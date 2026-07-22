# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Second ADR-042 migration: drain tokens out of ``config.toml [contexts.*]``.

The first migration (``config_migration.py``) consolidated every legacy shape
into ``config.toml [contexts.*]`` (``url``/``token`` + the ``api_*`` mirror). The
second revision moves credentials OUT of ``config.toml`` while KEEPING the named
contexts: every token goes to the per-server token store (``credential_store``),
and each ``[contexts.<name>]`` is rewritten **address-only** as ``{server = url}``
— a secret-free *global context*. So an old named connection ("prod") survives as
a global context you can still select project-lessly with ``--context prod``. The
old current-context pointer seeds ``[cli].default_context``.

Trigger: a context still carrying a token (or a legacy ``url``/``api_url`` without
``server``), or a stale current-context pointer. An already address-only
``[contexts.*]`` (what this migration and ``hop3 context add`` write) is a no-op.

Crash-safety (destructive, runs at first launch — same contract as stage 1):

- **Abort loud / change nothing** on a malformed ``config.toml``.
- **Copy-if-absent backup** to ``config.toml.pre-042s.bak`` before any write.
- **Write every token to the store FIRST** (the store's write is fsync'd), and
  rewrite ``config.toml`` only AFTER — so no token is ever stranded. This matters
  most for ``http(s)://`` servers, which cannot be re-minted over SSH.
- **Idempotent**: once the tokens are out and contexts are address-only, a no-op.
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
    """Drain tokens to the store; keep each context address-only (a global context).

    Returns human-readable notes (empty on the no-op path). Raises
    ``MigrationError`` (nothing changed on disk) on a malformed ``config.toml``.
    """
    config_path = config_dir / CONFIG_FILENAME
    if not config_path.is_file():
        return []

    data = _load_or_abort(config_path)
    contexts = data.get("contexts")
    if not isinstance(contexts, dict) or not contexts:
        return []  # no-op: no contexts at all
    if not _needs_migration(data, contexts):
        return []  # no-op: already address-only, no token, no stale pointer

    from hop3_cli.core import credential_store  # ruff:ignore[import-outside-top-level]

    # 1. Backup (copy-if-absent) BEFORE any mutation.
    backup = config_dir / (CONFIG_FILENAME + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(config_path, backup)
        _chmod_600(backup)

    # 2. Drain every token to the store (durable) and rewrite each context
    # address-only (``{server = url}``) — a secret-free global context.
    new_contexts, drained = _drain_and_convert(contexts, credential_store)

    # 3. Seed the default context from the old current-context pointer.
    pointer = _str(_pointer(data))
    default_context = pointer if pointer in new_contexts else None

    # 4. Rewrite config.toml: address-only contexts, no token, pointer -> default.
    new_config = {
        k: v for k, v in data.items() if k not in {"contexts", "current_context"}
    }
    if new_contexts:
        new_config["contexts"] = new_contexts
    cli = dict(new_config.get("cli") or {})
    cli.pop("current_context", None)
    if default_context:
        cli["default_context"] = default_context
    if cli:
        new_config["cli"] = cli
    else:
        new_config.pop("cli", None)
    atomic_write_toml(config_path, new_config)
    _chmod_600(config_path)

    summary = (
        f"Moved {len(drained)} server token(s) to the per-server store; "
        f"kept {len(new_contexts)} named context(s) by address (config.toml is "
        "secret-free)."
    )
    notes = [summary]
    if default_context:
        notes.append(f"Default context: {default_context!r}.")
    return notes


def _drain_and_convert(
    contexts: dict[str, Any], credential_store
) -> tuple[dict[str, Any], list[str]]:
    """Drain each context's token to the store; return (address-only contexts, drained)."""
    drained: list[str] = []
    new_contexts: dict[str, Any] = {}
    for name, block in contexts.items():
        if not isinstance(block, dict):
            continue
        server = _str(block.get("server") or block.get("url") or block.get("api_url"))
        token = _str(block.get("token") or block.get("api_token"))
        if server and token:
            credential_store.set_token(server, token)  # atomic + fsync'd
            drained.append(name)
        if server:
            new_contexts[name] = {"server": server}
    return new_contexts, drained


def _needs_migration(data: dict[str, Any], contexts: dict[str, Any]) -> bool:
    """True iff there is a token to drain, a legacy url to convert, or a stale pointer."""
    if _str(_pointer(data)):
        return True
    for block in contexts.values():
        if not isinstance(block, dict):
            continue
        if _str(block.get("token") or block.get("api_token")):
            return True
        # A legacy connection carries url/api_url but no 'server' yet.
        if _str(block.get("url") or block.get("api_url")) and not _str(
            block.get("server")
        ):
            return True
    return False


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
