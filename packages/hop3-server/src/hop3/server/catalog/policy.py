# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Catalog spec-validation gate (ADR 049 F7).

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

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from hop3.toolchains.python import unpinned_requirements

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_CATCHALL_HOST = "_"  # the nginx catch-all / default_server
_WILDCARD = "*"


class CatalogSpecError(Exception):
    """Raised when a catalog spec violates platform coexistence policy."""


def validate_catalog_spec(data: Mapping, app_id: str) -> None:
    """
    Reject a catalog spec that would hijack shared reverse-proxy routing.

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


def validate_catalog_app_files(app_dir: Path, app_id: str) -> None:
    """
    Reject a catalog app whose recipe cannot build on a node.

    A blueprint that fails to build is worse than a missing one: the operator
    installs it, the build aborts, and the app is left with nothing to run. The
    build-time rules therefore belong at publish time too, where they cost the
    release team one message instead of every user one broken install.

    Currently: an unpinned ``requirements.txt``, which the Python toolchain
    refuses as unreproducible. The rule is imported from the toolchain rather
    than restated, so the gate cannot drift from what a node enforces.

    Raises:
        CatalogSpecError: if the app's recipe would fail its build.
    """
    # Every advertised app must be verifiable. Without a check.py the platform
    # can say an app deployed and nothing more — and "it deployed" turned out
    # repeatedly not to mean "it works": apps served their login page perfectly
    # while rejecting every credential. A blueprint that ships no check makes
    # that indistinguishable from success, so it does not go in the catalog.
    if not (app_dir / "check.py").exists():
        msg = (
            f"Catalog app {app_id!r} ships no check.py, so installing it could "
            f"only ever prove that it started. Add a smoke test that signs in "
            f"and asserts a wrong password is refused (see an existing app's "
            f"check.py), or leave the app out of the catalog."
        )
        raise CatalogSpecError(msg)

    requirements = app_dir / "requirements.txt"
    if requirements.exists():
        _reject_unpinned(
            app_id, requirements.read_text(), "ships an unpinned requirements.txt"
        )

    # A build script that WRITES requirements.txt hides it from this gate: the
    # file does not exist until deploy time, so an unpinned set shipped and only
    # failed on the node. Read the heredoc it would write.
    for script in sorted(app_dir.glob("scripts/*.sh")):
        generated = _generated_requirements(script.read_text())
        if generated:
            _reject_unpinned(
                app_id,
                generated,
                f"generates an unpinned requirements.txt in scripts/{script.name}",
            )


def _generated_requirements(script: str) -> str:
    """
    The requirements.txt body a shell script writes via heredoc, if any.

    Matches ``cat > requirements.txt << 'EOF' ... EOF`` and its unquoted and
    ``>>`` variants. Deliberately narrow: it recognises the one idiom recipes
    actually use, and misses rather than guesses.
    """
    pattern = re.compile(
        r"cat\s*>>?\s*(?:\./)?requirements\.txt\s*<<[-\s]*['\"]?(\w+)['\"]?\s*\n(.*?)\n\1",
        re.DOTALL,
    )
    return "\n".join(match.group(2) for match in pattern.finditer(script))


def _reject_unpinned(app_id: str, text: str, what: str) -> None:
    """Refuse a requirement set the Python toolchain would reject on the node."""
    unpinned = unpinned_requirements(text)
    if not unpinned:
        return
    shown = ", ".join(unpinned[:5])
    msg = (
        f"Catalog app {app_id!r} {what}: {shown}. The Python toolchain refuses "
        f"it as unreproducible, so this blueprint would fail its build on every "
        f"node that installs it. Pin every dependency — `uv pip compile "
        f"requirements.in -o requirements.txt` — and re-publish."
    )
    raise CatalogSpecError(msg)
