# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""proxy ops: addon-exposure TCP forwarders (`hop3 addon expose`).

Each op validates args, writes/enables (or removes) the per-addon
``systemd-socket-proxyd`` unit pair via the ``proxy`` helper, updates
state.json, and returns the typed result. Atomicity mirrors the mount/firewall
ops: act first, persist state on success.

The unit name is composed *here* from validated ``addon_type`` + ``addon_name``;
a raw systemd unit name is never accepted off the wire, so a caller can only
ever act on a ``hop3-expose-<type>-<name>`` unit it owns. The forwarder
destination is hardcoded to loopback in the helper.
"""

from __future__ import annotations

from typing import Any

from hop3_rootd import proxy as px
from hop3_rootd.ops._base import OpContext, register
from hop3_rootd.protocol import Request
from hop3_rootd.state import StoredProxy
from hop3_rootd.validation import (
    validate_addon_name,
    validate_addon_type,
    validate_port,
    validate_source,
)

# --- proxy.add -----------------------------------------------------------


@register("proxy.add")
def add_proxy(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Create+enable a forwarder ``0.0.0.0:public_port`` → ``127.0.0.1:target_port``."""
    addon_type = validate_addon_type(req.args.get("addon_type"))
    addon_name = validate_addon_name(req.args.get("addon_name"))
    public_port = validate_port(req.args.get("public_port"))
    target_port = validate_port(req.args.get("target_port"))
    source = validate_source(req.args.get("source", "any"))
    applied_at = ctx.now_iso()

    result = px.add_proxy(
        addon_type, addon_name, public_port, target_port, exec=ctx.exec
    )

    ctx.state.proxies = [
        p
        for p in ctx.state.proxies
        if not (p.addon_type == addon_type and p.addon_name == addon_name)
    ]
    ctx.state.proxies.append(
        StoredProxy(
            addon_type=addon_type,
            addon_name=addon_name,
            unit=result["unit"],
            public_port=public_port,
            target_port=target_port,
            source=source,
            applied_at=applied_at,
        )
    )
    ctx.save_state()

    return {
        "addon_type": addon_type,
        "addon_name": addon_name,
        "source": source,
        "applied_at": applied_at,
        **result,
    }


# --- proxy.remove --------------------------------------------------------


@register("proxy.remove")
def remove_proxy(req: Request, ctx: OpContext) -> dict[str, Any]:
    """Stop+disable+delete an addon's forwarder and drop it from state.

    Idempotent: an addon that isn't exposed reports ``removed=False``. Always
    drops the (type, name) state row so a destroyed addon leaves no tracked
    proxy.
    """
    addon_type = validate_addon_type(req.args.get("addon_type"))
    addon_name = validate_addon_name(req.args.get("addon_name"))

    base = px.unit_base_name(addon_type, addon_name)
    result = px.remove_proxy(base, exec=ctx.exec)

    ctx.state.proxies = [
        p
        for p in ctx.state.proxies
        if not (p.addon_type == addon_type and p.addon_name == addon_name)
    ]
    ctx.save_state()

    return {"addon_type": addon_type, "addon_name": addon_name, **result}


# --- proxy.list ----------------------------------------------------------


@register("proxy.list", audit=False)
def list_proxies(req: Request, ctx: OpContext) -> dict[str, Any]:
    """List the addon forwarders rootd tracks (teardown-verification surface).

    Optional ``addon_type`` filter. After unexposing an addon the server calls
    proxy.list and expects it gone.
    """
    type_filter = req.args.get("addon_type")
    if type_filter is not None:
        validate_addon_type(type_filter)
        proxies = [p for p in ctx.state.proxies if p.addon_type == type_filter]
    else:
        proxies = list(ctx.state.proxies)

    return {
        "proxies": [
            {
                "addon_type": p.addon_type,
                "addon_name": p.addon_name,
                "unit": p.unit,
                "public_port": p.public_port,
                "target_port": p.target_port,
                "source": p.source,
                "applied_at": p.applied_at,
            }
            for p in proxies
        ]
    }
