# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Implicit app resolution (ADR 036 D7).

When a command requires an `--app` argument and none is given on the command
line, resolve one from a layered chain of sources, highest-priority first:

    1. `--app <name>` / `-a <name>` flag (handled before resolution; if set,
       we never call here)
    2. `$HOP3_APP` env var
    3. `.hop3-app` file in CWD or any ancestor directory up to `$HOME`
    4. `[cli].app` in `hop3.toml` in CWD or any ancestor
    5. Active context's `default_app` (set via `hop3 use` or
       `hop3 context use --app`)

A sixth optional source — "git remote named `hop3`" — is in the ADR but not
implemented in this first cut.

The resolver returns both the resolved app name and a short string describing
the source, so callers can show provenance (e.g., via `--why`) or error
helpfully when nothing resolves.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tomllib

if TYPE_CHECKING:
    from hop3_cli.config import Config


@dataclass(frozen=True)
class AppResolution:
    """Result of resolving the current app."""

    app: str | None
    source: (
        str  # Short human-readable description ("env", "flag", "context default", ...)
    )
    # A longer trace (list of "tried source -> result") for `--why`.
    trace: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return bool(self.app)


def resolve_app(
    cli_app: str | None,
    config: Config,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> AppResolution:
    """Resolve the effective app name per the D7 chain.

    Args:
        cli_app: App passed explicitly via `--app` / `-a` (highest priority).
        config: Config object (used for context default_app).
        cwd: Directory to start looking from (defaults to process CWD).
        env: Environment mapping (defaults to os.environ); mainly for testing.
        home: User home directory (defaults to $HOME); mainly for testing.
    """
    cwd = cwd or Path.cwd()
    if env is None:
        env = dict(os.environ)
    home = home or Path.home()

    trace: list[str] = []

    # Source 1: explicit --app flag
    if cli_app:
        trace.append(f"flag: --app {cli_app!r}")
        return AppResolution(app=cli_app, source="--app flag", trace=tuple(trace))

    trace.append("flag --app: (not given)")

    # Source 2: $HOP3_APP
    env_app = (env.get("HOP3_APP") or "").strip()
    if env_app:
        trace.append(f"$HOP3_APP: {env_app!r}")
        return AppResolution(app=env_app, source="$HOP3_APP", trace=tuple(trace))
    trace.append("$HOP3_APP: (not set)")

    # Source 3: .hop3-app file in CWD or any ancestor up to $HOME
    found_file, found_app = _search_dotfile(cwd, home, ".hop3-app")
    if found_app:
        trace.append(f".hop3-app ({found_file}): {found_app!r}")
        return AppResolution(
            app=found_app,
            source=f".hop3-app at {found_file}",
            trace=tuple(trace),
        )
    trace.append(".hop3-app: (not found)")

    # Source 4: hop3.toml [cli].app in CWD or any ancestor
    found_toml, toml_app = _search_hop3_toml(cwd, home)
    if toml_app:
        trace.append(f"hop3.toml ({found_toml}) [cli].app: {toml_app!r}")
        return AppResolution(
            app=toml_app,
            source=f"hop3.toml [cli].app at {found_toml}",
            trace=tuple(trace),
        )
    trace.append("hop3.toml [cli].app: (not set)")

    # Source 5: active context's default_app
    ctx_name = config.get_current_context_name()
    if ctx_name:
        ctx_app = config.get_default_app()
        if ctx_app:
            trace.append(f"context {ctx_name!r} default_app: {ctx_app!r}")
            return AppResolution(
                app=ctx_app,
                source=f"context {ctx_name!r} default app",
                trace=tuple(trace),
            )
        trace.append(f"context {ctx_name!r} default_app: (not set)")
    else:
        trace.append("context: (none active)")

    return AppResolution(app=None, source="(unresolved)", trace=tuple(trace))


def _search_dotfile(
    start: Path, stop_at: Path, filename: str
) -> tuple[Path | None, str | None]:
    """Search upward from `start` for a dotfile, stopping at `stop_at` (inclusive).

    Returns (path_of_file, contents) or (None, None).
    """
    # Walk from `start` up. Include `stop_at` itself in the search.
    current = start.resolve()
    stop_at = stop_at.resolve()
    while True:
        candidate = current / filename
        if candidate.is_file():
            try:
                return candidate, candidate.read_text().strip()
            except OSError:
                return None, None
        if current in {stop_at, current.parent}:
            break
        current = current.parent
    return None, None


def _search_hop3_toml(start: Path, stop_at: Path) -> tuple[Path | None, str | None]:
    """Search upward for a hop3.toml with [cli].app set."""
    current = start.resolve()
    stop_at = stop_at.resolve()
    while True:
        candidate = current / "hop3.toml"
        if candidate.is_file():
            try:
                data = tomllib.loads(candidate.read_text())
                cli = data.get("cli", {})
                app = cli.get("app") if isinstance(cli, dict) else None
                if isinstance(app, str) and app.strip():
                    return candidate, app.strip()
            except (OSError, tomllib.TOMLDecodeError):
                pass  # Silently skip unparseable hop3.toml
        if current in {stop_at, current.parent}:
            break
        current = current.parent
    return None, None


def format_trace(resolution: AppResolution) -> str:
    """Render a resolution trace as a human-readable multi-line string."""
    lines = ["[resolution]"]
    for entry in resolution.trace:
        lines.append(f"  {entry}")
    if resolution.resolved:
        lines.append(f"  -> app = {resolution.app!r} (source: {resolution.source})")
    else:
        lines.append("  -> app = (unresolved)")
    return "\n".join(lines)
