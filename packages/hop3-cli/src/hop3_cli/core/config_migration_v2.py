# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Second ADR-042 migration: drain ``config.toml [contexts.*]`` into the store.

The first migration (``config_migration.py``) consolidated every legacy shape
into ``config.toml [contexts.*]`` (``url``/``token`` + the ``api_*`` mirror). The
second revision moves credentials OUT of ``config.toml``: every token goes to the
per-server token store (``credential_store``), ``config.toml`` is left
secret-free, and the old global current-context pointer is dropped (context is
per-project now). The old current-context seeds the default-server.

Trigger: any ``[contexts.*]`` present in ``config.toml``. Idempotent once gone.

Crash-safety (destructive, runs at first launch — same contract as stage 1):

- **Abort loud / change nothing** on a malformed ``config.toml``.
- **Copy-if-absent backup** to ``config.toml.pre-042s.bak`` before any write.
- **Write every token to the store FIRST** (the store's write is fsync'd), and
  remove ``[contexts.*]`` from ``config.toml`` only AFTER — so no token is ever
  stranded. This matters most for ``http(s)://`` servers, which cannot be
  re-minted over SSH; ``ssh://`` servers could re-auth, but we never rely on it.
- **Idempotent**: once ``[contexts.*]`` is gone, a zero-write no-op.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from typing import TYPE_CHECKING, Any

import tomllib

from hop3_cli.core.local_overlay import atomic_write_toml

if TYPE_CHECKING:
    from pathlib import Path

CONFIG_FILENAME = "config.toml"
BACKUP_SUFFIX = ".pre-042s.bak"


class MigrationError(Exception):
    """Abort the second migration without changing anything on disk."""


def migrate_config_to_token_store(config_dir: Path) -> list[str]:
    """Drain ``config.toml [contexts.*]`` tokens into the store; leave it secret-free.

    Returns human-readable notes (empty on the no-op path). Raises
    ``MigrationError`` (nothing changed on disk) on a malformed ``config.toml``.
    """
    config_path = config_dir / CONFIG_FILENAME
    if not config_path.is_file():
        return []

    data = _load_or_abort(config_path)
    contexts = data.get("contexts")
    if not isinstance(contexts, dict) or not contexts:
        return []  # no-op: nothing to drain

    from hop3_cli.core import credential_store  # noqa: PLC0415

    # 1. Backup (copy-if-absent) BEFORE any mutation.
    backup = config_dir / (CONFIG_FILENAME + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(config_path, backup)
        _chmod_600(backup)

    # 2. Drain every token to the store (durable) BEFORE removing it from config.
    drained: list[str] = []
    for name, block in contexts.items():
        if not isinstance(block, dict):
            continue
        url = _str(block.get("url") or block.get("api_url"))
        token = _str(block.get("token") or block.get("api_token"))
        if url and token:
            credential_store.set_token(url, token)  # atomic + fsync'd
            drained.append(name)

    # 3. Seed the default-server from the old current-context's address.
    default_server = None
    pointer = _str(_pointer(data))
    if pointer and isinstance(contexts.get(pointer), dict):
        block = contexts[pointer]
        default_server = _str(block.get("url") or block.get("api_url"))

    # 4. Rewrite config.toml secret-free: drop [contexts.*] + the pointer.
    new_config = {
        k: v for k, v in data.items() if k not in {"contexts", "current_context"}
    }
    cli = dict(new_config.get("cli") or {})
    cli.pop("current_context", None)
    if default_server:
        cli["default_server"] = default_server
    if cli:
        new_config["cli"] = cli
    else:
        new_config.pop("cli", None)
    atomic_write_toml(config_path, new_config)
    _chmod_600(config_path)

    summary = (
        f"Moved {len(drained)} server token(s) to the per-server store; "
        "config.toml is now secret-free."
    )
    notes = [summary]
    if default_server:
        notes.append(f"Default server: {default_server}.")
    return notes


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _pointer(data: dict[str, Any]) -> Any:
    """The old current-context pointer (``[cli].current_context`` or top-level)."""
    cli = data.get("cli")
    if isinstance(cli, dict) and cli.get("current_context"):
        return cli["current_context"]
    return data.get("current_context")


def _load_or_abort(path: Path) -> dict[str, Any]:
    """Parse ``path`` as TOML; malformed → abort loud (change nothing)."""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = (
            f"{path} is malformed ({exc}). Migration aborted; nothing changed. "
            "Fix or remove the file, then retry."
        )
        raise MigrationError(msg) from exc


def _chmod_600(path: Path) -> None:
    """Best-effort 0o600 (config.toml may transiently hold a JWT mid-migration)."""
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
