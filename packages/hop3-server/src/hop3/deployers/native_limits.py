# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: TRY003, EM101, EM102
# _NotEnforcedError is internal control flow: raised + caught within this module,
# its message folded into the abort diagnosis. Inline messages read better here.

"""Native ``[limits]`` enforcement via cgroup v2 (ADR 046 §3 / P2.2).

Docker apps get their caps from the compose generator at build time. Native /
Nix apps run on the host, so their caps are placed by ``hop3-rootd`` into a
cgroup v2 leaf and the app's PIDs are migrated into it.

Three entry points, mirroring ``fixed_ports.py``:

- **enforce** (post-start): once the app is RUNNING (its PIDs exist), write the
  resolved cap to the leaf and attach the PIDs. Strict mode (default) aborts the
  deploy if it can't — a declared cap that isn't applied is a looks-capped-but-
  isn't lie. Best-effort mode records ``limits_enforced=unenforced`` and warns.
- **reattach** (periodic): re-migrate live PIDs into the leaf so a whole-vassal
  respawn (the Emperor forks a fresh master outside the leaf) or a rootd restart
  (reconcile re-creates the leaf + caps but not PID membership) can't silently
  uncap a running app. Best-effort, idempotent, quiet on success.
- **remove** (teardown): kill + drop the leaf so destroy leaves no stale cap.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

from hop3.config import HopConfig
from hop3.deployers.limits import LimitsError, resolve_limits, to_cgroup_args
from hop3.lib import Diagnosis, abort_with_diagnosis, log
from hop3.lib.rootd import (
    LocalRootdClient,
    RootdError,
    RootdUnavailableError,
)
from hop3.run.reaper import app_pids

if TYPE_CHECKING:
    from hop3.orm import App
    from hop3.project.config import AppConfig


class _NotEnforcedError(Exception):
    """Internal: enforcement couldn't be completed (rootd down/rejected, no PIDs)."""


def format_limits_detail(limits: dict[str, Any]) -> str:
    """One-line caps summary for ``hop3 app status`` (e.g. 'memory=512M cpu=1.5')."""
    return " ".join(f"{k}={v}" for k, v in limits.items())


def enforce_native_limits(app: App, app_config: AppConfig) -> None:
    """Place a native/Nix app's processes under its resolved cgroup cap.

    Runs AFTER the app is confirmed RUNNING (PIDs exist only then). Re-resolves
    the declared ``[limits]`` against the server defaults/ceilings — the pre-build
    pass already aborted on a ceiling breach, so this re-resolve is to obtain the
    effective caps, not to re-validate. Docker apps are skipped (compose already
    applied their caps). An empty resolution drops any stale leaf so a redeploy
    that removed ``[limits]`` doesn't leave a ghost cap.
    """
    if app.runtime and "docker" in app.runtime:
        return  # docker caps come from the compose generator (build time)

    cfg = HopConfig.get_instance()
    try:
        resolved = resolve_limits(
            app_config.hop3_config.limits, cfg.limits_defaults(), cfg.limits_ceilings()
        )
    except LimitsError as e:
        # The pre-build pass already validated the ceiling, but HopConfig reads
        # the policy fresh each time, so an operator lowering a ceiling mid-deploy
        # could trip it here. Fail with a structured diagnosis, not a traceback.
        abort_with_diagnosis(
            Diagnosis(
                component="Limits",
                action="enforce [limits] resource caps",
                reason=f"[limits] for '{app.name}' breached the server ceiling: {e}",
                hint=(
                    "the server-wide [limits] ceiling may have changed since the "
                    "build. Lower the app's cap or ask the operator to restore it."
                ),
                troubleshooting=["See ADR 046 §3 (resource caps)"],
            )
        )

    if resolved.is_empty():
        # Redeploy that dropped [limits]: tear down any prior leaf AND clear the
        # recorded state, else status keeps reporting a cap that no longer exists
        # and the periodic re-attach keeps poking a dead leaf.
        remove_native_limits(app.name)
        app.limits_enforced = ""
        app.limits_detail = ""
        return

    detail = format_limits_detail(resolved.as_dict())
    try:
        _apply_cgroup(app.name, to_cgroup_args(resolved))
    except _NotEnforcedError as e:
        if cfg.LIMITS_STRICT:
            _abort_unenforced(app.name, detail, str(e))
        app.limits_enforced = "unenforced"
        app.limits_detail = f"{detail} (NOT enforced: {e})"
        log(
            f"[limits] for '{app.name}' NOT enforced (best-effort, "
            f"LIMITS_STRICT=false): {e}",
            level=1,
            fg="yellow",
        )
        return

    app.limits_enforced = "native"
    app.limits_detail = detail
    log(f"[limits] enforced for '{app.name}' via cgroup: {detail}", level=2, fg="green")


def reattach_native_limits(app_name: str) -> None:
    """Idempotent re-attach of an app's live PIDs to its cgroup leaf.

    Run periodically over RUNNING native-capped apps by the state-sync service.
    Covers two cases the deploy-time attach can't: the Emperor respawning a whole
    vassal (the new master forks outside the leaf — cgroup v2 inheritance only
    carries workers forked from an already-attached master), and a rootd restart
    (its reconcile re-creates the leaf + caps but does not re-add PID membership).
    Best-effort: does not propagate a rootd error (so the babysitter loop keeps
    going), but a failure is logged — a re-attach that silently fails would leave
    an app recorded as capped while running uncapped.
    """
    pids = app_pids(app_name)
    if not pids:
        return
    try:
        with LocalRootdClient() as client:
            result = client.call(
                "cgroup.attach_pids", {"app_name": app_name, "pids": pids}
            )
    except RootdError as e:
        log(
            f"[limits] re-attach for '{app_name}' failed: {e}; the app may be "
            f"running uncapped until the next cycle",
            level=1,
            fg="yellow",
        )
        return
    failed = result.get("failed", [])
    if failed:
        log(
            f"[limits] re-attach for '{app_name}': {len(failed)} process(es) "
            f"could not be placed under the cap",
            level=1,
            fg="yellow",
        )


def remove_native_limits(app_name: str) -> None:
    """Kill + drop the app's cgroup leaf on teardown (best-effort, never raises).

    Idempotent on the rootd side (a missing leaf reports absent). Destroy reaps
    the processes first, so the leaf is empty by the time this runs; this just
    clears the leaf and the stored cap so no ghost cgroup survives the app.
    """
    with suppress(RootdError), LocalRootdClient() as client:
        client.call("cgroup.remove", {"app_name": app_name})


def _apply_cgroup(app_name: str, args: dict[str, Any]) -> None:
    """Ensure the slice, write the cap, attach the PIDs. Raises _NotEnforcedError."""
    pids = app_pids(app_name)
    if not pids:
        raise _NotEnforcedError("no running processes found to place under the cap")
    try:
        with LocalRootdClient() as client:
            client.call("cgroup.ensure_slice")
            client.call("cgroup.set_limits", {"app_name": app_name, **args})
            result = client.call(
                "cgroup.attach_pids", {"app_name": app_name, "pids": pids}
            )
    except RootdUnavailableError as e:
        raise _NotEnforcedError(f"hop3-rootd is unavailable: {e}") from e
    except RootdError as e:
        raise _NotEnforcedError(f"hop3-rootd rejected the cgroup op: {e}") from e

    failed = result.get("failed", [])
    if failed:
        raise _NotEnforcedError(f"{len(failed)} process(es) could not be attached")


def _abort_unenforced(app_name: str, detail: str, reason: str) -> None:
    abort_with_diagnosis(
        Diagnosis(
            component="Limits",
            action="enforce [limits] resource caps",
            reason=f"could not apply caps ({detail}) for '{app_name}': {reason}",
            hint=(
                "native enforcement needs hop3-rootd with cgroup v2. Start or "
                "repair hop3-rootd, or set LIMITS_STRICT=false to deploy uncapped "
                "(status then reports the cap as NOT enforced)."
            ),
            troubleshooting=[
                "systemctl status hop3-rootd",
                "journalctl -u hop3-rootd --no-pager | tail -50",
            ],
        )
    )
