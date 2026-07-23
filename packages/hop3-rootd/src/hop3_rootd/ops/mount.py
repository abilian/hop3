# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""
mount ops: native ``[[volumes]]`` realization (ADR 046 §2 / P2.1).

Each op handler validates args, performs the mount/umount via the ``mount``
helper (raising MountError on kernel failure), updates state.json, and returns
the typed result. Atomicity mirrors firewall/cgroup ops: act on the kernel
first, persist state on success (ADR 041 §7).

This slice covers ``tmpfs`` (sized RAM scratch), ``unmount``, and ``list``
(the teardown-verification surface). ``mount.bind`` and its operator
allow-list land in a follow-up.
"""

from __future__ import annotations

from typing import Any

from hop3_rootd import mount as mt
from hop3_rootd.ops._base import OpContext, register
from hop3_rootd.protocol import Request
from hop3_rootd.state import StoredMount
from hop3_rootd.validation import (
    validate_app_name,
    validate_bind_source,
    validate_mount_mode,
    validate_read_only,
    validate_size_bytes,
    validate_volume_target,
)

# --- mount.tmpfs ---------------------------------------------------------


@register("mount.tmpfs")
def mount_tmpfs(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Mount a sized tmpfs at the app's target and record it in state."""
    app_name = validate_app_name(req.args.get("app_name"))
    target = validate_volume_target(req.args.get("target"))
    size_bytes = validate_size_bytes(req.args.get("size_bytes"))
    mode = validate_mount_mode(req.args.get("mode"))
    applied_at = ctx.now_iso()

    result = mt.mount_tmpfs(app_name, target, size_bytes, mode, exec=ctx.exec)

    ctx.state.mounts = [
        m
        for m in ctx.state.mounts
        if not (m.app_name == app_name and m.target == target)
    ]
    ctx.state.mounts.append(
        StoredMount(
            app_name=app_name,
            target=target,
            type="tmpfs",
            source=None,
            applied_at=applied_at,
        )
    )
    ctx.save_state()

    return {
        "app_name": app_name,
        "target": target,
        "mountpoint": result["mountpoint"],
        "type": "tmpfs",
        "applied_at": applied_at,
    }


# --- mount.bind ----------------------------------------------------------


@register("mount.bind")
def mount_bind(req: Request, ctx: OpContext) -> dict[str, Any]:
    """
    Bind-mount an operator-allowed host path at the app's target.

    The source must pass rootd's own allow-list check (default-deny); a denied
    or missing source aborts loudly. Records the resolved source in state.
    """
    app_name = validate_app_name(req.args.get("app_name"))
    target = validate_volume_target(req.args.get("target"))
    source = validate_bind_source(req.args.get("source"))
    read_only = validate_read_only(req.args.get("read_only"))
    applied_at = ctx.now_iso()

    result = mt.mount_bind(app_name, target, source, read_only=read_only, exec=ctx.exec)

    ctx.state.mounts = [
        m
        for m in ctx.state.mounts
        if not (m.app_name == app_name and m.target == target)
    ]
    ctx.state.mounts.append(
        StoredMount(
            app_name=app_name,
            target=target,
            type="bind",
            source=result["source"],
            applied_at=applied_at,
        )
    )
    ctx.save_state()

    return {
        "app_name": app_name,
        "target": target,
        "mountpoint": result["mountpoint"],
        "type": "bind",
        "source": result["source"],
        "read_only": read_only,
        "applied_at": applied_at,
    }


# --- mount.unmount -------------------------------------------------------


@register("mount.unmount")
def unmount(req: Request, ctx: OpContext) -> dict[str, Any]:
    """
    Unmount the app's target and drop it from state (teardown).

    Idempotent: a target that isn't mounted reports ``unmounted=False,
    kernel_state=absent``. Always drops the (app, target) state row so a
    destroyed app leaves no tracked mount.
    """
    app_name = validate_app_name(req.args.get("app_name"))
    target = validate_volume_target(req.args.get("target"))

    result = mt.unmount(app_name, target, exec=ctx.exec)

    ctx.state.mounts = [
        m
        for m in ctx.state.mounts
        if not (m.app_name == app_name and m.target == target)
    ]
    ctx.save_state()

    return {"app_name": app_name, "target": target, **result}


# --- mount.list ----------------------------------------------------------


@register("mount.list", audit=False)
def list_mounts(req: Request, ctx: OpContext) -> dict[str, Any]:
    """
    List the mounts rootd tracks (optionally for one app).

    This is the teardown-verification surface: after unmounting an app's
    volumes the server calls mount.list({app_name}) and expects it empty.
    """
    app_filter = req.args.get("app_name")
    if app_filter is not None:
        validate_app_name(app_filter)
        mounts = ctx.state.mounts_for_app(app_filter)
    else:
        mounts = list(ctx.state.mounts)

    return {
        "mounts": [
            {
                "app_name": m.app_name,
                "target": m.target,
                "type": m.type,
                "source": m.source,
                "applied_at": m.applied_at,
            }
            for m in mounts
        ]
    }
