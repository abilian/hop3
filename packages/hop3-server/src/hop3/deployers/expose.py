# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Addon exposure: make a 127.0.0.1-only addon reachable on a public host port.

`hop3 addon expose` allocates a stable, persisted host port, opens the firewall
for it (rootd ``firewall.add_rule``), and stands up a per-addon
``systemd-socket-proxyd`` forwarder (rootd ``proxy.add``) so external clients
reach the addon's loopback port. The exposure is recorded as a :class:`PortClaim`
(``app_id`` null, ``addon_*`` set), sharing the one host-wide port space with app
fixed-ports so the two can never collide.

Sibling of ``fixed_ports.py`` and modelled on it: claim → firewall → (here also)
proxy, with the ``rule_id``/``proxy_unit`` stored for teardown. Unlike fixed
ports, the firewall + proxy are *mandatory* (an exposure with no listener is
meaningless), so a rootd failure aborts loudly and rolls back rather than
degrading.
"""

from __future__ import annotations

import random
import socket
from contextlib import suppress
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import urlparse, urlunparse

from sqlalchemy.exc import IntegrityError

from hop3.core.plugins import get_addon
from hop3.lib import Diagnosis, abort_with_diagnosis, log
from hop3.lib.rootd import LocalRootdClient, RootdError, RootdUnavailableError
from hop3.orm import PortClaim, PortClaimRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, scoped_session

    # The session a repository carries (advanced_alchemy types it as a union).
    DbSession = Session | scoped_session[Session]

# Public-port range: above the well-known/registered service ports and below
# Linux's default ephemeral range (32768+), so an allocated port doesn't fight
# outbound source-port allocation.
PORT_RANGE_LOW = 20000
PORT_RANGE_HIGH = 32767


def connection_url(details: dict[str, str]) -> str | None:
    """
    Pick the one ``*_URL`` entry from a get_connection_details() dict.

    Engine-agnostic: every addon returns exactly one (DATABASE_URL, REDIS_URL, …).
    """
    for key, value in details.items():
        if key.endswith("_URL"):
            return value
    return None


def _port_is_free(port: int) -> bool:
    """True if nothing currently holds ``port`` on 0.0.0.0 (a real bind probe)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def allocate_public_port(repo: PortClaimRepository, protocol: str = "tcp") -> int:
    """
    Pick a random unused host port: free in the claim table AND on the socket.

    Aborts loudly if the range is exhausted rather than returning a busy port.
    """
    candidates = list(range(PORT_RANGE_LOW, PORT_RANGE_HIGH + 1))
    random.SystemRandom().shuffle(candidates)
    for port in candidates:
        if repo.find_active(port, protocol) is not None:
            continue
        if _port_is_free(port):
            return port
    abort_with_diagnosis(
        Diagnosis(
            component="Addon",
            action="allocate a public port for exposure",
            reason=f"no free port in [{PORT_RANGE_LOW}, {PORT_RANGE_HIGH}]",
            hint="unexpose an addon to free a port, or widen the range",
        )
    )
    raise AssertionError  # unreachable: abort_with_diagnosis above is NoReturn


def _rewrite_url(url: str, host: str, port: int) -> str:
    """Rebuild a connection URL with the external host + public port."""
    parsed = urlparse(url)
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    return urlunparse(parsed._replace(netloc=f"{userinfo}{host}:{port}"))


def _firewall_tag(addon_type: str, addon_name: str) -> str:
    """Owner tag stored on the claim + passed to the firewall (for the sweep)."""
    return f"expose-{addon_type}-{addon_name}"


def _abort_no_url(addon_type: str, addon_name: str) -> NoReturn:
    abort_with_diagnosis(
        Diagnosis(
            component="Addon",
            action=f"expose {addon_type} addon '{addon_name}'",
            reason="the addon exposes no connection URL / port",
            hint="only network addons (postgres/mysql/redis) can be exposed",
        )
    )


def _rollback_partial(
    rule_id: str | None, claim: PortClaim, db_session: DbSession
) -> None:
    """Undo a half-done exposure: remove any firewall rule, drop the claim row."""
    if rule_id:
        with suppress(RootdError, RootdUnavailableError), LocalRootdClient() as client:
            client.call("firewall.remove_rule", {"rule_id": rule_id})
    with suppress(Exception):
        db_session.delete(claim)
        db_session.flush()


def expose_addon(
    addon_type: str,
    addon_name: str,
    *,
    source: str,
    host: str,
    db_session: DbSession,
) -> dict[str, Any]:
    """
    Expose an addon on a public host port. Idempotent.

    If the addon is already exposed, returns its existing endpoint (no second
    port allocated). Otherwise allocates a port, writes the claim, opens the
    firewall and stands up the forwarder — ordered, with rollback on any
    failure so there is never a half-open exposure.
    """
    repo = PortClaimRepository(session=db_session)
    details = get_addon(addon_type, addon_name).get_connection_details()
    url = connection_url(details)
    if not url:
        _abort_no_url(addon_type, addon_name)
    parsed = urlparse(url)
    target_port = parsed.port
    if not target_port:
        _abort_no_url(addon_type, addon_name)

    existing = repo.find_by_addon(addon_type, addon_name)
    if existing is not None:
        return {
            "type": addon_type,
            "addon_name": addon_name,
            "host": host,
            "public_port": existing.number,
            "source": existing.source,
            "url": _rewrite_url(url, host, existing.number),
            "already_exposed": True,
        }

    public_port = allocate_public_port(repo)
    tag = _firewall_tag(addon_type, addon_name)
    claim = PortClaim(
        app_id=None,
        number=public_port,
        protocol="tcp",
        app_name=tag,
        addon_type=addon_type,
        addon_name=addon_name,
        source=source,
    )
    db_session.add(claim)
    try:
        db_session.flush()
    except IntegrityError:
        # Lost an allocation race; the unique constraint is the backstop.
        db_session.rollback()
        abort_with_diagnosis(
            Diagnosis(
                component="Addon",
                action=f"claim public port {public_port}",
                reason="the port was taken by a concurrent operation",
                hint="retry the expose command",
            )
        )

    rule_id: str | None = None
    try:
        with LocalRootdClient() as client:
            fw = client.call(
                "firewall.add_rule",
                {
                    "port": public_port,
                    "protocol": "tcp",
                    "source": source,
                    "app_name": tag,
                    "description": f"hop3 expose {addon_type}/{addon_name}",
                },
            )
            rule_id = fw.get("rule_id")
            claim.rule_id = rule_id
            proxy = client.call(
                "proxy.add",
                {
                    "addon_type": addon_type,
                    "addon_name": addon_name,
                    "public_port": public_port,
                    "target_port": target_port,
                    "source": source,
                },
            )
            claim.proxy_unit = proxy.get("unit")
    except (RootdError, RootdUnavailableError) as e:
        _rollback_partial(rule_id, claim, db_session)
        abort_with_diagnosis(
            Diagnosis(
                component="Addon",
                action=f"expose {addon_type} addon '{addon_name}'",
                reason=str(e),
                hint=(
                    "hop3-rootd must be running and able to open the firewall "
                    "and create the forwarder; the exposure was rolled back."
                ),
                troubleshooting=[
                    "journalctl -u hop3-rootd --no-pager | tail -50",
                ],
            )
        )

    log(
        f"Exposed {addon_type} addon '{addon_name}' on port {public_port} "
        f"(source {source})",
        level=2,
        fg="green",
    )
    return {
        "type": addon_type,
        "addon_name": addon_name,
        "host": host,
        "public_port": public_port,
        "source": source,
        "url": _rewrite_url(url, host, public_port),
        "already_exposed": False,
    }


def unexpose_addon(addon_type: str, addon_name: str, *, db_session: DbSession) -> bool:
    """
    Tear down an addon's exposure. Idempotent; returns False if not exposed.

    Drops the claim row first (so the host port is reclaimable even if rootd is
    down), then best-effort closes the firewall and removes the forwarder. A
    rootd failure here is not fatal: the claim is gone, so the orphaned unit is
    swept by rootd's startup ``reconcile_proxies``.
    """
    repo = PortClaimRepository(session=db_session)
    claim = repo.find_by_addon(addon_type, addon_name)
    if claim is None:
        return False

    rule_id = claim.rule_id
    tag = claim.app_name
    # Step 1 — free the registry row first.
    db_session.delete(claim)
    db_session.flush()
    log(f"Released exposure claim for {addon_type} addon '{addon_name}'", level=2)

    # Step 2 — close firewall + remove forwarder (best-effort; reconcile is the
    # completeness backstop if rootd is unreachable right now).
    try:
        with LocalRootdClient() as client:
            rule_ids = {rule_id} if rule_id else set()
            with suppress(RootdError):
                listed = client.call("firewall.list_rules", {"app_name": tag})
                rule_ids.update(r.get("rule_id") for r in listed.get("rules", []))
            for rid in rule_ids:
                if rid:
                    with suppress(RootdError):
                        client.call("firewall.remove_rule", {"rule_id": rid})
            with suppress(RootdError):
                client.call(
                    "proxy.remove",
                    {"addon_type": addon_type, "addon_name": addon_name},
                )
    except (RootdError, RootdUnavailableError) as e:
        log(
            f"Could not fully tear down exposure of '{addon_name}' (best-effort, "
            f"rootd reconcile will sweep the orphan): {e}",
            level=1,
            fg="yellow",
        )
    return True
