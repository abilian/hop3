# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared hop3.toml reader: walk upward to find one, parse it safely.

Five callers used to maintain their own copy of "walk from CWD upward,
stopping at $HOME, parse the first hop3.toml found, swallow TOML errors":

- ``core.resolution._resolve_from_hop3_toml`` (app resolution sources 4-6)
- ``core.resolution._declared_context_names``
- ``core.resolution._context_server_from_hop3_toml``
- ``core.project_guard._read_cwd_metadata_id``
- ``core.deploy_preview._read_nearest_hop3_toml``
- ``commands.local.project_context_cmd.find_project_hop3_toml``

Each had subtly different error-swallowing. Consolidating prevents the
class of bug where one walker tightens its boundary and the others miss
the update.

The two public helpers are:

- ``first_hop3_toml(start, home) -> (path, data)``
- ``iter_hop3_toml(start, home) -> Iterator[(path, data)]``

Both return ``(Path | None, dict)`` tuples; ``data`` is ``{}`` on read
or parse failure (callers never observe exceptions from this module).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import tomllib

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

HOP3_TOML = "hop3.toml"


def first_hop3_toml(start: Path, home: Path) -> tuple[Path | None, dict[str, Any]]:
    """Find the nearest hop3.toml at or above ``start``, capped at ``home``.

    Returns ``(path, parsed_data)`` for the first file found, or
    ``(None, {})`` when no hop3.toml exists in the walked range.
    Unparseable files yield ``(path, {})`` so the caller can distinguish
    "file was here but couldn't read it" from "no file at all" via the
    presence of ``path``.
    """
    for path, data in iter_hop3_toml(start, home):
        return path, data
    return None, {}


def iter_hop3_toml(start: Path, home: Path) -> Iterator[tuple[Path, dict[str, Any]]]:
    """Walk upward from ``start`` to ``home``, yielding each hop3.toml found.

    Most callers want the first match (``first_hop3_toml``); the
    iterator form exists for hypothetical "merge layered configs"
    consumers and to keep the walk itself in one place.
    """
    current = start.resolve()
    stop_at = home.resolve()
    while True:
        candidate = current / HOP3_TOML
        if candidate.is_file():
            yield candidate, read_hop3_toml(candidate)
        if current in {stop_at, current.parent}:
            return
        current = current.parent


def read_hop3_toml(path: Path) -> dict[str, Any]:
    """Parse a single hop3.toml; return ``{}`` on OSError or TOMLDecodeError.

    Public because ``project_context_cmd`` opens specific hop3.toml paths
    (already located by ``find_project_hop3_toml``) and needs the same
    error-swallowing contract as the walk-and-parse callers.
    """
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
