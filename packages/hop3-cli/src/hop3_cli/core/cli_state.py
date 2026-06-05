# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Reader and writer for ``~/.config/hop3-cli/state.toml`` (ADR 042 §CLI verbs).

Holds the **CLI's transient operator state** — currently just the
"global default server" pointer that ``hop3 server use <name>`` writes.
Logically distinct from:

- ``config.toml`` — operator preferences (theme, default verbosity, …);
  largely unaffected by ADR 042.
- ``servers.toml`` — the server-binding registry.
- ``.hop3-local.toml`` — per-checkout context selection.

Shape::

    current_server = "prod"

Kept tiny on purpose. Step 4 introduces just the one field; future
operator-state additions (e.g. "last successful login", "preferred
deploy strategy") can grow the file without touching the existing
shape.

This file is read on every CLI invocation that touches a server (so
``hop3 deploy`` etc. can resolve the implicit server) and written by
``hop3 server use <name>``. Atomic + 0o600 because the value identifies
the operator's preferred deployment target — not strictly a secret but
worth keeping out of world-readable scope.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

from hop3_cli.core.local_overlay import atomic_write_toml

STATE_TOML_FILENAME = "state.toml"


@dataclass(frozen=True)
class CliState:
    """Materialised view of the nearest ``state.toml``.

    Frozen for the same reason as ServerRegistry: writes always go
    through ``save_state`` returning a fresh instance, so callers
    can't mutate a shared view.
    """

    path: Path
    current_server: str | None = None
    data: dict[str, Any] | None = None  # raw, for forward-compat


def default_state_path() -> Path:
    """Resolve the default ``~/.config/hop3-cli/state.toml`` location."""
    from platformdirs import user_config_dir  # noqa: PLC0415

    return Path(user_config_dir("hop3-cli", "Abilian SAS")) / STATE_TOML_FILENAME


def load_state(path: Path | None = None) -> CliState:
    """Load the state file (or return an empty state if no file)."""
    target = path or default_state_path()
    if not target.is_file():
        return CliState(path=target, current_server=None, data={})
    try:
        with target.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return CliState(path=target, current_server=None, data={})

    cs = data.get("current_server")
    current_server = cs if isinstance(cs, str) and cs.strip() else None
    return CliState(path=target, current_server=current_server, data=data)


def save_state(state: CliState) -> Path:
    """Persist ``state`` atomically to its path.

    The state file is chmod 0o600 for symmetry with servers.toml — the
    operator's deployment-target pointer isn't a secret but isn't
    something we want world-readable on a multi-user host either.
    """
    target = state.path
    target.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = dict(state.data or {})
    if state.current_server:
        data["current_server"] = state.current_server
    else:
        data.pop("current_server", None)
    atomic_write_toml(target, data)
    with contextlib.suppress(OSError):
        os.chmod(target, 0o600)
    return target


def set_current_server(name: str | None, path: Path | None = None) -> Path:
    """Convenience: load → set current_server → save. Returns target path."""
    state = load_state(path)
    updated = CliState(
        path=state.path,
        current_server=name or None,
        data=state.data,
    )
    return save_state(updated)


def get_current_server(path: Path | None = None) -> str | None:
    """Convenience reader. None when no state file or no pointer set."""
    return load_state(path).current_server
