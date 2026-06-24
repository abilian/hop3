# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Project-mismatch sanity guard for destructive commands (ADR 042 §D14).

When the CLI is invoked in a directory whose ``hop3.toml [metadata].id``
does not match the resolved app, AND the resolved app came from a
non-CWD source (env var, server-level default, or a flag pointing
somewhere else), the destructive verb refuses to run unless the
operator passes ``--force``.

This is the belt to ``[metadata].id``'s suspenders. The resolution
chain already prefers the CWD project (source #6) over the server-
level default (source #8), so this guard only fires when something
*explicitly* forces a different target — the case where the operator
should be required to confirm "yes, I really mean it".

The "CWD-rooted vs not" decision is made against the typed
``AppSource`` kind on the AppResolution (see ``resolution.is_cwd_rooted``),
not by string-matching the human-readable ``source`` field — so renames
to the source descriptors can't silently disable the guard.

Applies to: ``deploy``, ``restart``, ``config set``, ``app destroy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_cli.core.hop3_toml import first_hop3_toml
from hop3_cli.core.resolution import is_cwd_rooted

if TYPE_CHECKING:
    from hop3_cli.core.resolution import AppSource


@dataclass(frozen=True)
class ProjectMismatch:
    """Result of the project-mismatch check.

    Attributes:
        is_mismatch: True iff the guard should fire.
        cwd_app: The app declared in CWD's hop3.toml [metadata].id, or
            None when no hop3.toml is present.
        resolved_app: The resolved app name from the chain.
        resolved_source: The source string from AppResolution.
        message: A formatted multi-line refusal message ready to print
            to stderr. Empty string when is_mismatch is False.
    """

    is_mismatch: bool
    cwd_app: str | None
    resolved_app: str
    resolved_source: str
    message: str = ""


def check_project_mismatch(
    resolved_app: str,
    resolved_source: str,
    resolved_kind: AppSource,
    verb: str,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> ProjectMismatch:
    """Compare the resolved app against the CWD project's [metadata].id.

    Args:
        resolved_app: The non-empty app name produced by the resolver.
        resolved_source: The ``source`` string from AppResolution; carried
            verbatim into the refusal message so the operator can see
            *why* the wrong app was picked.
        resolved_kind: The typed ``AppSource`` from AppResolution. Used
            (in preference to the source string) to decide whether the
            resolution was CWD-rooted — see ``resolution.is_cwd_rooted``.
        verb: The destructive verb name (``"deploy"`` etc.) — interpolated
            into the refusal message.
        cwd: Directory to start looking from (defaults to ``Path.cwd()``).
        home: User home directory (defaults to ``Path.home()``); the
            search for the nearest hop3.toml stops here.

    Returns:
        ProjectMismatch with ``is_mismatch=True`` only when:
        1. CWD has a hop3.toml with ``[metadata].id`` set;
        2. that id is different from ``resolved_app``;
        3. ``resolved_kind`` is NOT one of the CWD-rooted kinds.
    """
    cwd = cwd or Path.cwd()
    home = home or Path.home()

    cwd_app = _read_cwd_metadata_id(cwd, home)
    if cwd_app is None:
        return ProjectMismatch(
            is_mismatch=False,
            cwd_app=None,
            resolved_app=resolved_app,
            resolved_source=resolved_source,
        )

    if cwd_app == resolved_app:
        return ProjectMismatch(
            is_mismatch=False,
            cwd_app=cwd_app,
            resolved_app=resolved_app,
            resolved_source=resolved_source,
        )

    # Names differ. If the resolution came from a CWD-rooted source, that's
    # fine — the operator explicitly mapped this project to a different app name
    # via [cli].app, or via a context whose selection was itself CWD-rooted
    # (AppSource.CONTEXT_APP; an AMBIENT context selection is NOT cwd-rooted and
    # falls through to the refusal below — ADR 042 r2 footgun protection).
    if is_cwd_rooted(resolved_kind):
        return ProjectMismatch(
            is_mismatch=False,
            cwd_app=cwd_app,
            resolved_app=resolved_app,
            resolved_source=resolved_source,
        )

    # Mismatch: build the refusal message.
    message = _format_mismatch_message(
        verb=verb,
        cwd_app=cwd_app,
        resolved_app=resolved_app,
        resolved_source=resolved_source,
    )
    return ProjectMismatch(
        is_mismatch=True,
        cwd_app=cwd_app,
        resolved_app=resolved_app,
        resolved_source=resolved_source,
        message=message,
    )


def _read_cwd_metadata_id(cwd: Path, home: Path) -> str | None:
    """Read ``[metadata].id`` from the nearest hop3.toml at-or-above CWD."""
    _, data = first_hop3_toml(cwd, home)
    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        mid = metadata.get("id")
        if isinstance(mid, str) and mid.strip():
            return mid.strip()
    return None


def _format_mismatch_message(
    *, verb: str, cwd_app: str, resolved_app: str, resolved_source: str
) -> str:
    """Build the multi-line refusal message exactly as ADR 042 §D14 specifies.

    The ``resolved_source`` is captured as a diagnostic appendix on a
    separate trailing line — useful for the operator to know *why* the
    mismatch happened (was it $HOP3_APP? a stale server default?) — but
    it lives below the two remediation bullets to keep the ADR's literal
    headline + bullet structure intact.
    """
    return (
        f"Refusing to {verb}: resolved app {resolved_app!r} does not match "
        f"project {cwd_app!r} in ./hop3.toml.\n"
        f"\n"
        f"  - To {verb} the project you are standing in:\n"
        f"      hop3 {verb}  (after `hop3 context use <name>` to pick a target)\n"
        f"  - To {verb} the resolved app from any directory:\n"
        f"      hop3 {verb} --force\n"
        f"\n"
        f"(resolved app came from: {resolved_source})"
    )
