# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Fixed host-port handling: claim registry, pre-flight refusal, firewall.

HTTP/HTTPS is multiplexed by the reverse proxy (nginx vhosts by ``Host:``), so
many apps share :80/:443 with no conflict. Non-HTTP services (SMTP, XMPP, RTMP,
Matrix federation, …) have no proxy and no virtual hosting: the app binds the
host port directly, so exactly one app can own a given ``(number, protocol)``.

Apps declare these in ``[[ports]]``. This module:

- **claims** each declared port in a host-wide registry *before* build, refusing
  a conflicting second app with a clear diagnosis (the claim lives in the deploy
  session, so a failed deploy rolls it back — no leak);
- **reconciles** on redeploy — a port the app no longer declares is released
  (firewall closed, claim dropped) so it can't leak or block another app;
- **opens** the firewall for the claimed ports once the deploy succeeds
  (best-effort: conflict prevention is DB-based and does not need rootd);
- **closes** the firewall on teardown.

Fixed ports take effect for apps that bind the host port directly (native / nix
builds). Docker-deployed apps would also need the container to *publish* the port
to the host — that is a follow-up (see ADR 045); for now they are claimed (so the
conflict check still applies) but the firewall is not opened.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from hop3.lib import Diagnosis, abort_with_diagnosis, log
from hop3.lib.rootd import LocalRootdClient, RootdError, RootdUnavailableError
from hop3.orm import PortClaim, PortClaimRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App
    from hop3.project.config import AppConfig


def _abort_conflict(number: int, protocol: str, holder: str) -> None:
    abort_with_diagnosis(
        Diagnosis(
            component="Deployer",
            action=f"claim port {number}/{protocol}",
            reason=f"port {number}/{protocol} is already used by app '{holder}'",
            hint=(
                "a fixed host port can serve only one app (there is no reverse "
                "proxy for non-HTTP ports) — remove the other app, or change one "
                "of them to a different port"
            ),
            troubleshooting=[
                f"hop3 apps  # find the app holding {number}/{protocol}",
                f"hop3 app destroy {holder}  # free the port",
            ],
        )
    )


def _close_firewall_rule(rule_id: str | None) -> None:
    """Best-effort close of a single firewall rule (never raises)."""
    if not rule_id:
        return
    with suppress(RootdError), LocalRootdClient() as client:
        client.call("firewall.remove_rule", {"rule_id": rule_id})


def claim_fixed_ports(
    app: App, app_config: AppConfig, db_session: Session | None
) -> None:
    """Pre-flight: reconcile + claim the app's declared ``[[ports]]``.

    Runs BEFORE build. First releases any claim this app held for a port it no
    longer declares (so a removed/changed port doesn't leak or block others).
    Then, for each declared port: if another app holds ``(number, protocol)``,
    abort with a clear diagnosis; otherwise record the claim in the deploy
    session — rolled back with the session if the deploy later fails. A
    savepoint-guarded flush turns a concurrent-deploy race into the same clear
    diagnosis rather than an opaque IntegrityError.
    """
    if db_session is None:
        return

    declared = app_config.ports
    repo = PortClaimRepository(session=db_session)
    declared_keys = {
        (p["number"], (p.get("protocol") or "tcp").lower()) for p in declared
    }

    # Reconcile: drop claims for ports this app declared before but no longer does.
    for claim in repo.get_by_app_id(app.id):
        if (claim.number, claim.protocol) not in declared_keys:
            _close_firewall_rule(claim.rule_id)
            db_session.delete(claim)
            log(
                f"Released fixed port {claim.number}/{claim.protocol} "
                f"(no longer declared) for '{app.name}'",
                level=2,
                fg="blue",
            )
    db_session.flush()

    for spec in declared:
        number = spec["number"]
        protocol = (spec.get("protocol") or "tcp").lower()
        source = spec.get("source") or "any"

        existing = repo.find_active(number, protocol)
        if existing is not None and existing.app_id != app.id:
            _abort_conflict(number, protocol, existing.app_name)
        if existing is not None:
            # Already this app's claim (idempotent redeploy). If only the source
            # changed, re-scope it: close the stale firewall rule and clear the
            # rule_id so open_fixed_ports re-applies with the new source. Without
            # this a redeployed source edit would be silently ignored.
            if existing.source != source:
                _close_firewall_rule(existing.rule_id)
                existing.source = source
                existing.rule_id = None
                log(
                    f"Re-scoped fixed port {number}/{protocol} to source "
                    f"{source} for '{app.name}'",
                    level=2,
                    fg="blue",
                )
            continue

        # The find_active check above handles the normal case with a clear
        # message. The unique constraint is the race backstop: if another deploy
        # committed the port between our check and our flush — or our read
        # snapshot was stale (each deploy runs in its own session/connection, and
        # WAL gives long-lived transactions a fixed snapshot) — the flush raises
        # IntegrityError. Roll the failed flush back so the session is usable,
        # then re-read on a fresh snapshot to name the *real* holder (a query on
        # the poisoned session would itself raise; the bare rollback fixes that).
        # The deploy aborts regardless — its caller also rolls back.
        db_session.add(
            PortClaim(
                app_id=app.id,
                number=number,
                protocol=protocol,
                app_name=app.name,
                source=source,
            )
        )
        try:
            db_session.flush()
        except IntegrityError:
            db_session.rollback()
            holder = repo.find_active(number, protocol)
            _abort_conflict(
                number, protocol, holder.app_name if holder else "another app"
            )
        log(
            f"Claimed fixed port {number}/{protocol} for '{app.name}'",
            level=2,
            fg="blue",
        )


def open_fixed_ports(app: App, db_session: Session | None) -> None:
    """On a successful deploy, open the firewall for the app's claimed ports.

    Best-effort: conflict prevention is DB-based and does not need rootd, so an
    unreachable rootd is a warning, not a failure. Docker apps are skipped (their
    declared ports aren't published to the host yet — see module docstring). The
    rootd rule id is stored on the claim so teardown can remove it.
    """
    if db_session is None:
        return
    repo = PortClaimRepository(session=db_session)

    if app.runtime and "docker" in app.runtime:
        if repo.get_by_app_id(app.id):
            log(
                "Fixed [[ports]] are claimed but not opened for Docker-deployed "
                "apps — the container does not publish them to the host yet "
                "(ADR 045 follow-up). Use a native/nix build for direct host "
                "ports.",
                level=1,
                fg="yellow",
            )
        return

    claims = [c for c in repo.get_by_app_id(app.id) if not c.rule_id]
    if not claims:
        return

    try:
        with LocalRootdClient() as client:
            for claim in claims:
                result = client.call(
                    "firewall.add_rule",
                    {
                        "port": claim.number,
                        "protocol": claim.protocol,
                        "source": claim.source,
                        "app_name": app.name,
                        "description": f"hop3 fixed port for {app.name}",
                    },
                )
                claim.rule_id = result.get("rule_id")
                log(
                    f"Opened firewall for {claim.number}/{claim.protocol} "
                    f"(rule {claim.rule_id})",
                    level=2,
                    fg="green",
                )
    except RootdUnavailableError:
        log(
            "hop3-rootd is unavailable: fixed ports are claimed but NOT opened "
            "in the firewall — external clients can't reach them until rootd "
            "applies the rules. Start hop3-rootd and redeploy.",
            level=1,
            fg="yellow",
        )
    except RootdError as e:
        # rootd was reachable and *rejected* the command (e.g. a malformed nft
        # rule, a kernel error). Unlike an unavailable rootd — which reconcile
        # re-applies later — this fails the same way every time, so degrading
        # would deploy an app whose declared port never opens while reporting
        # success. Abort loudly instead of swallowing it as a warning.
        abort_with_diagnosis(
            Diagnosis(
                component="Deployer",
                action="open the firewall for the app's fixed [[ports]]",
                reason=str(e),
                hint=(
                    "hop3-rootd rejected the firewall rule, so the declared "
                    "port would not be reachable. This is a platform/rootd bug "
                    "— check the rootd logs for the failing nft command."
                ),
                troubleshooting=[
                    "journalctl -u hop3-rootd --no-pager | tail -50",
                    "hop3 app logs <app>",
                ],
            )
        )


def release_fixed_ports(app: App, db_session: Session | None) -> None:
    """On teardown, fully release the app's fixed ports: firewall *and* registry.

    Two steps, in priority order:

    1. **Drop the claim rows** so the host-wide port is free. This is done here —
       not left to the App-delete cascade — so the port is reclaimed even if a
       later teardown step (filesystem / Docker cleanup) fails before the App row
       is deleted. A stranded claim blocks *every* future deploy of that port, so
       freeing it must not depend on the rest of destroy succeeding. (The caller
       commits; the cascade on App delete is then just a harmless backstop.)
    2. **Close the firewall** — best-effort, never blocks destroy. Removes rules
       by stored id *and* by app name (so a rule whose id never made it back to
       the DB is still reclaimed).
    """
    if db_session is None:
        return
    repo = PortClaimRepository(session=db_session)
    claims = repo.get_by_app_id(app.id)
    if not claims:
        return

    # Step 1 — free the registry rows first, so the port is reclaimable even if
    # the best-effort firewall close below fails (the caller commits the delete).
    # rule_ids are read off the claim objects before deletion (still in memory).
    rule_ids = {c.rule_id for c in claims if c.rule_id}
    for claim in claims:
        db_session.delete(claim)
    log(f"Released fixed-port claims of '{app.name}'", level=2, fg="blue")

    # Step 2 — close the firewall (best-effort, never blocks destroy).
    try:
        with LocalRootdClient() as client:
            # Also sweep any rule rootd still has for this app (orphan safety).
            with suppress(RootdError):
                listed = client.call("firewall.list_rules", {"app_name": app.name})
                rule_ids.update(r.get("rule_id") for r in listed.get("rules", []))
            for rule_id in rule_ids:
                if rule_id:
                    with suppress(RootdError):
                        client.call("firewall.remove_rule", {"rule_id": rule_id})
            log(f"Closed firewall for fixed ports of '{app.name}'", level=2, fg="blue")
    except RootdError as e:
        log(
            f"Could not close firewall for fixed ports (best-effort): {e}",
            level=1,
            fg="yellow",
        )
