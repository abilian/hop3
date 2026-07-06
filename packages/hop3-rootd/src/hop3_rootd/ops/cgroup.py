# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""cgroup ops: native ``[limits]`` enforcement via cgroup v2 (ADR 046 §3 / P2.2).

Each op handler:
  - validates args (raises ValidationError on bad input)
  - performs the cgroup fs mutation (raises CgroupError on kernel failure)
  - updates state.json via ctx.save_state()
  - returns the typed result

Atomicity mirrors firewall ops: apply to the kernel first, persist state on
success (ADR 041 §7). A crash between the two leaves a leaf the reconcile can
re-assert or remove from state — the safe direction.
"""

from __future__ import annotations

from typing import Any

from hop3_rootd import cgroup as cg
from hop3_rootd.ops._base import OpContext, register
from hop3_rootd.protocol import Request
from hop3_rootd.state import StoredCgroup
from hop3_rootd.validation import (
    validate_app_name,
    validate_cgroup_limits,
    validate_pid_list,
)

# --- cgroup.ensure_slice -------------------------------------------------


@register("cgroup.ensure_slice", audit=False)
def ensure_slice(_req: Request, _ctx: OpContext) -> dict[str, Any]:
    """Create hop3.slice and enable the required controllers (idempotent).

    Read-ish/idempotent capability probe — raises CgroupUnavailableError
    (→ kernel_error) when the host can't enforce limits, so the caller aborts
    in strict mode rather than deploying a looks-capped-but-isn't app.
    """
    return cg.ensure_slice()


# --- cgroup.set_limits ---------------------------------------------------


@register("cgroup.set_limits")
def set_limits(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Create/refresh an app's cgroup leaf and write its caps.

    Writes the kernel first, then records (replacing any prior caps for the
    app) in state so reconcile can re-assert the leaf after a rootd restart.
    """
    limits = validate_cgroup_limits(req.args)
    applied_at = ctx.now_iso()

    result = cg.set_limits(
        limits.app_name,
        memory_max=limits.memory_max,
        cpu_max=limits.cpu_max,
        pids_max=limits.pids_max,
    )

    ctx.state.cgroups = [c for c in ctx.state.cgroups if c.app_name != limits.app_name]
    ctx.state.cgroups.append(
        StoredCgroup(
            app_name=limits.app_name,
            memory_max=limits.memory_max,
            cpu_max=limits.cpu_max,
            pids_max=limits.pids_max,
            applied_at=applied_at,
        )
    )
    ctx.save_state()

    return {
        "app_name": limits.app_name,
        "cgroup_path": result["cgroup_path"],
        "applied": result["applied"],
        "applied_at": applied_at,
    }


# --- cgroup.attach_pids --------------------------------------------------


@register("cgroup.attach_pids")
def attach_pids(req: Request, _ctx: OpContext) -> dict[str, Any]:
    """Migrate the given PIDs into the app's leaf.

    Returns ``{attached, failed}``; a non-empty ``failed`` is the caller's
    signal that enforcement is incomplete (strict mode aborts). No state
    change — PIDs aren't persisted (they belong to the Emperor).
    """
    app_name = validate_app_name(req.args.get("app_name"))
    pids = validate_pid_list(req.args.get("pids"))
    result = cg.attach_pids(app_name, pids)
    return {"app_name": app_name, **result}


# --- cgroup.remove -------------------------------------------------------


@register("cgroup.remove")
def remove(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Kill the app's cgroup subtree and remove the leaf (teardown).

    Idempotent: a missing leaf reports ``removed=False, kernel_state=absent``.
    Always drops the app from state so a destroyed app leaves no stored cap.
    """
    app_name = validate_app_name(req.args.get("app_name"))
    result = cg.remove(app_name)

    ctx.state.cgroups = [c for c in ctx.state.cgroups if c.app_name != app_name]
    ctx.save_state()

    return {"app_name": app_name, **result}


# --- cgroup.read ---------------------------------------------------------


@register("cgroup.read", audit=False)
def read(req: Request, _ctx: OpContext) -> dict[str, Any]:
    """Read the app leaf's current caps, usage, and OOM-kill count.

    Used by ``hop3 app status`` to show enforced caps and surface OOM kills.
    Raises a ValidationError on a bad name and CgroupError if there is no leaf.
    """
    app_name = validate_app_name(req.args.get("app_name"))
    return {"app_name": app_name, **cg.read(app_name)}
