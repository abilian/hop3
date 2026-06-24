# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Catalog spec-validation gate (ADR 049 F7).

A *verified* catalog spec is authentic but still potentially hostile to its
neighbours. This gate refuses a spec that would claim an **unmanaged shared
resource** and break the "apps must coexist" invariant (CLAUDE.md).

The one such resource a `hop3.toml` can actually express is the reverse-proxy
default server: an app whose ``[domains].list`` is the nginx catch-all ``"_"``
(or a wildcard host) would shadow every other app on the box. A catalog blueprint
must never pin that — the operator assigns the real hostname at install time.

Other coexistence concerns are already handled by the platform and are therefore
*not* gated here: ``[build].builder`` is constrained by the hop3.toml schema;
``[[ports]]`` fixed host ports are registered and conflict-refused by Hop3;
``[[addons]]`` are provisioned per-app. So this gate is deliberately narrow — it
guards the genuine, expressible hijack, not a checklist of fields that cannot
cause harm.

The function is reusable as the *publish-time* gate (the primary place to catch a
bad spec, before signing) and as a *load-time* backstop on the node.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_CATCHALL_HOST = "_"  # the nginx catch-all / default_server
_WILDCARD = "*"


class CatalogSpecError(Exception):
    """Raised when a catalog spec violates platform coexistence policy."""


def validate_catalog_spec(data: Mapping, app_id: str) -> None:
    """Reject a catalog spec that would hijack shared reverse-proxy routing.

    Args:
        data: the parsed ``hop3.toml`` of a catalog app.
        app_id: the app id, for an actionable error message.

    Raises:
        CatalogSpecError: if the spec claims the catch-all/default host or a
            wildcard host.
    """
    for host in _declared_hosts(data):
        if host == _CATCHALL_HOST:
            msg = (
                f"Catalog app {app_id!r} declares the nginx catch-all host '_', "
                "which would hijack the reverse-proxy default server and shadow "
                "every other app on the host. Catalog apps must not pin a "
                "catch-all/default host; the operator sets the domain at install."
            )
            raise CatalogSpecError(msg)
        if _WILDCARD in host:
            msg = (
                f"Catalog app {app_id!r} declares the wildcard host {host!r}; "
                "wildcard/catch-all hosts are not allowed in catalog apps."
            )
            raise CatalogSpecError(msg)


def _declared_hosts(data: Mapping) -> Iterator[str]:
    """Yield every hostname the spec declares (top-level and per-context)."""
    domains = data.get("domains")
    if isinstance(domains, Mapping):
        # `list` is the TOML key; `hosts` is the schema field name (both accepted).
        yield from _as_str_list(domains.get("list"))
        yield from _as_str_list(domains.get("hosts"))

    # ADR 042 r2: per-environment contexts live under the plural `contexts` key,
    # and a context's domains use the same [domains] shape (a `list`/`hosts`
    # table) — so they must run the same host-safety checks as top-level domains.
    contexts = data.get("contexts")
    if isinstance(contexts, Mapping):
        for ctx in contexts.values():
            if not isinstance(ctx, Mapping):
                continue
            dom = ctx.get("domains")
            if isinstance(dom, Mapping):
                yield from _as_str_list(dom.get("list"))
                yield from _as_str_list(dom.get("hosts"))
            else:
                yield from _as_str_list(dom)  # tolerate a bare list defensively


def _as_str_list(value: object) -> Iterator[str]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item
