# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Shared hop3.toml reader: walk upward to find one, parse it safely.

Five callers used to maintain their own copy of "walk from CWD upward,
stopping at $HOME, parse the first hop3.toml found, swallow TOML errors":

- ``core.resolution._resolve_from_hop3_toml`` (app resolution sources 4-6)
- ``core.resolution._declared_context_names``
- ``core.resolution._context_server_from_hop3_toml``
- ``core.project_guard._read_cwd_metadata_id``
- ``core.deploy_preview._read_nearest_hop3_toml``

Each had subtly different error-swallowing. Consolidating prevents the
class of bug where one walker tightens its boundary and the others miss
the update.

The two public helpers are:

- ``first_hop3_toml(start, home) -> (path, data)``
- ``iter_hop3_toml(start, home) -> Iterator[(path, data)]``

Both return ``(Path | None, dict)`` tuples. A file that is there but cannot
be read or parsed raises ``ConfigError`` naming it: a malformed hop3.toml
read as empty dropped ``[build].ignore`` (so a deploy uploaded the files it
excluded) and skipped the project checks, with nothing said.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hop3_cli.core.toml_file import read_toml

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

HOP3_TOML = "hop3.toml"


def first_hop3_toml(start: Path, home: Path) -> tuple[Path | None, dict[str, Any]]:
    """
    Find the nearest hop3.toml at or above ``start``, capped at ``home``.

    Returns ``(path, parsed_data)`` for the first file found, or
    ``(None, {})`` when no hop3.toml exists in the walked range.
    """
    for path, data in iter_hop3_toml(start, home):
        return path, data
    return None, {}


def iter_hop3_toml(start: Path, home: Path) -> Iterator[tuple[Path, dict[str, Any]]]:
    """
    Walk upward from ``start`` to ``home``, yielding each hop3.toml found.

    Most callers want the first match (``first_hop3_toml``); the
    iterator form exists for hypothetical "merge layered configs"
    consumers and to keep the walk itself in one place.
    """
    current = start.resolve()
    stop_at = home.resolve()
    while True:
        candidate = current / HOP3_TOML
        if candidate.is_file():
            yield candidate, read_toml(candidate)
        if current in {stop_at, current.parent}:
            return
        current = current.parent
