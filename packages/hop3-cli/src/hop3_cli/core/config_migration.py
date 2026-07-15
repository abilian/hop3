# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""One-shot ADR-042 (revised) config migration.

Drains every legacy server/context shape a real machine may carry into a
single ``config.toml`` whose ``[contexts.*]`` blocks ARE the connections
(ADR 042 §Migration — "One Context, One Connection").

Three on-disk shapes coexist on real machines and are all handled here:

1. **legacy** ``config.toml [contexts.*]`` with ``api_url``/``api_token``;
2. **post-Step-4** ``servers.toml [servers.*]`` with ``url``/``token``;
3. **post-old-lazy-migration**: ``config.toml`` was renamed to
   ``config.toml.pre-042.bak`` and a ``servers.toml`` was written. We read the
   ``.pre-042.bak`` for any ``current_context`` pointer and fold the records in.

The current-context pointer is read from BOTH ``state.toml current_server`` and
the legacy ``config.toml [.] current_context``; on conflict ``current_server``
wins (newer ADR-042 location).

Design guarantees (the migration is destructive, runs on first launch, must be
safe even if the process is killed mid-way):

- **Fail loud, change nothing** on malformed input (a typo'd ``config.toml``
  must never be read as "empty → discard the operator's contexts").
- **Copy-if-absent backups** to ``*.pre-042r.bak`` before any mutation, so a
  resumed run never overwrites the true original with an already-mutated file.
- **Strict write order**: backups → write ``config.toml`` → strip
  ``current_server`` → delete ``servers.toml`` LAST. All writes go through
  ``atomic_write_toml`` (tmpfile+fsync+rename+dir-fsync).
- **Idempotent**: a fully-migrated tree (no ``servers.toml``, no
  ``current_server``, new-shape ``config.toml``) is a zero-write no-op.
- **Downgrade window**: each context mirrors ``url``/``token`` AND
  ``api_url``/``api_token`` for one release so a downgrade to the prior binary
  doesn't silently lose configured servers (mirror removed in a follow-up).
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
SERVERS_FILENAME = "servers.toml"
STATE_FILENAME = "state.toml"
OLD_LAZY_BACKUP_FILENAME = "config.toml.pre-042.bak"
BACKUP_SUFFIX = ".pre-042r.bak"

# Fields a unified context (connection) carries. `default_app` is intentionally
# absent — app resolution is CWD-rooted now (ADR 042 §App resolution).
_CONNECTION_FIELDS = (
    "ssh_user",
    "ssh_port",
    "ssh_key",
    "ssl_cert",
    "verify_ssl",
    "protected",
)


class MigrationError(Exception):
    """Raised to ABORT the migration without changing anything on disk.

    The message is operator-facing and names the offending file + next action.
    """


def migrate_legacy_config_042(config_dir: Path) -> list[str]:
    """Migrate the CLI config dir in place to the ADR-042 unified shape.

    Args:
        config_dir: The CLI config directory (holds config.toml / servers.toml /
            state.toml). Passed explicitly so tests run fully isolated.

    Returns:
        A list of human-readable notes (empty on the no-op fast path). Callers
        print them to stderr.

    Raises:
        MigrationError: on malformed input or a dangling current-context pointer.
            Nothing on disk has been changed when this is raised.
    """
    config_path = config_dir / CONFIG_FILENAME
    servers_path = config_dir / SERVERS_FILENAME
    state_path = config_dir / STATE_FILENAME
    old_bak_path = config_dir / OLD_LAZY_BACKUP_FILENAME

    config_data = _load_toml_or_abort(config_path)
    state_data = _load_toml_or_abort(state_path)
    current_server = _str_or_none(state_data.get("current_server"))

    # --- Fast no-op: nothing legacy to drain. Zero writes/fsync. ---
    # (`hop3 version`/`hop3 help` must never touch disk on a fresh or
    # already-migrated machine.) "Nothing to do" means: no servers.toml, no
    # `current_server`, no legacy-shaped contexts in config.toml, and not the
    # shape-3 state (config.toml gone, .pre-042.bak left by the old migration).
    legacy_in_config = config_path.exists() and _has_legacy_contexts(config_data)
    shape3 = (not config_path.exists()) and old_bak_path.exists()
    if (
        not servers_path.exists()
        and not current_server
        and not legacy_in_config
        and not shape3
    ):
        return []

    # --- Gather records + the legacy pointer from every shape ---
    # Shape 3: config.toml is gone; read the old lazy-migration backup instead.
    source_config = config_data
    if not config_path.exists() and old_bak_path.exists():
        source_config = _load_toml_or_abort(old_bak_path)

    records, dropped_default_app = _gather_records(source_config, servers_path)
    pointer = _resolve_pointer(
        current_server, config_data, source_config, config_path.exists(), records
    )
    _apply_consolidation(
        config_dir=config_dir,
        config_data=config_data,
        source_config=source_config,
        config_exists=config_path.exists(),
        state_data=state_data,
        current_server=current_server,
        records=records,
        pointer=pointer,
    )
    return _notes(records, dropped_default_app, pointer)


def _gather_records(
    source_config: dict[str, Any], servers_path: Path
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Build the merged connection records from legacy contexts + servers.toml.

    Returns ``(records, dropped_default_app)``. On a same-name collision the
    token-bearing record wins (``_merge_prefer_token``).
    """
    records: dict[str, dict[str, Any]] = {}
    dropped = False
    for name, block in _contexts_of(source_config).items():
        unified, had_default_app = _to_connection(block)
        records[name] = unified
        dropped = dropped or had_default_app
    # servers.toml (parsed defensively; refuse to delete a broken one).
    for name, block in _servers_of_or_abort(servers_path).items():
        unified, had_default_app = _to_connection(block)
        dropped = dropped or had_default_app
        records[name] = (
            _merge_prefer_token(records[name], unified) if name in records else unified
        )
    return records, dropped


def _resolve_pointer(
    current_server: str | None,
    config_data: dict[str, Any],
    source_config: dict[str, Any],
    config_exists: bool,
    records: dict[str, dict[str, Any]],
) -> str | None:
    """Pick the current-context pointer; abort loud if it names no record.

    ``current_server`` (newer ADR-042 location) wins over the legacy
    ``current_context``.
    """
    pointer = current_server or _str_or_none(source_config.get("current_context"))
    if config_exists:
        pointer = (
            current_server
            or _str_or_none(config_data.get("current_context"))
            or pointer
        )
    if pointer and pointer not in records:
        msg = (
            f"Current-context pointer {pointer!r} names no known context "
            f"(have: {', '.join(sorted(records)) or '(none)'}). "
            "Migration aborted; nothing changed. Fix state.toml / config.toml."
        )
        raise MigrationError(msg)
    return pointer


def _apply_consolidation(
    *,
    config_dir: Path,
    config_data: dict[str, Any],
    source_config: dict[str, Any],
    config_exists: bool,
    state_data: dict[str, Any],
    current_server: str | None,
    records: dict[str, dict[str, Any]],
    pointer: str | None,
) -> None:
    """Backups → write config.toml → strip current_server → delete servers.toml.

    The order matters: ``servers.toml`` (the "not done yet" marker) is
    deleted LAST, and all backups are taken (copy-if-absent) before any write.
    """
    config_path = config_dir / CONFIG_FILENAME
    servers_path = config_dir / SERVERS_FILENAME
    state_path = config_dir / STATE_FILENAME

    _backup_if_absent(config_path, config_dir / (CONFIG_FILENAME + BACKUP_SUFFIX))
    _backup_if_absent(servers_path, config_dir / (SERVERS_FILENAME + BACKUP_SUFFIX))
    _backup_if_absent(state_path, config_dir / (STATE_FILENAME + BACKUP_SUFFIX))

    # Consolidated config, preserving unrelated keys (theme, etc.).
    new_config = _base_config(config_data, source_config, config_exists)
    new_config["contexts"] = {
        name: _with_downgrade_mirror(block) for name, block in records.items()
    }
    new_config.pop("current_context", None)
    cli_section = dict(new_config.get("cli") or {})
    cli_section.pop("current_context", None)
    if pointer:
        cli_section["current_context"] = pointer
        new_config["current_context"] = pointer  # top-level mirror (current reader)
    if cli_section:
        new_config["cli"] = cli_section
    atomic_write_toml(config_path, new_config)
    _chmod_600(config_path)

    if current_server:
        new_state = {k: v for k, v in state_data.items() if k != "current_server"}
        if new_state:
            atomic_write_toml(state_path, new_state)
            _chmod_600(state_path)
        else:
            state_path.unlink()

    if servers_path.exists():
        servers_path.unlink()  # LAST — absence is the "done" marker.


def _notes(
    records: dict[str, dict[str, Any]],
    dropped_default_app: bool,
    pointer: str | None,
) -> list[str]:
    notes = [
        (
            f"Migrated {len(records)} context(s) into {CONFIG_FILENAME}: "
            f"{', '.join(sorted(records)) or '(none)'}."
        )
    ]
    if dropped_default_app:
        notes.append(
            "Dropped per-server default_app — the app is now resolved from the "
            "project directory (hop3.toml / --app)."
        )
    if pointer:
        notes.append(f"Current context: {pointer}.")
    return notes


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _load_toml_or_abort(path: Path) -> dict[str, Any]:
    """Parse ``path`` as TOML. Missing file → ``{}``. Malformed → abort loud.

    A malformed config must NEVER be silently treated as empty — that would
    discard the operator's contexts. We raise (changing nothing) instead.
    """
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = (
            f"{path} is malformed ({exc}). Migration aborted; nothing changed. "
            "Fix or remove the file, then retry."
        )
        raise MigrationError(msg) from exc


def _servers_of_or_abort(servers_path: Path) -> dict[str, dict[str, Any]]:
    """Return servers.toml's ``[servers.*]`` table, aborting on a broken file.

    We must refuse to DELETE a servers.toml we couldn't parse (it would lose
    the operator's records), so a parse failure aborts the whole migration.
    """
    if not servers_path.exists():
        return {}
    data = _load_toml_or_abort(servers_path)  # abort message names the file
    servers = data.get("servers")
    return (
        {n: b for n, b in servers.items() if isinstance(b, dict)}
        if isinstance(servers, dict)
        else {}
    )


def _contexts_of(config_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contexts = config_data.get("contexts")
    return (
        {n: b for n, b in contexts.items() if isinstance(b, dict)}
        if isinstance(contexts, dict)
        else {}
    )


def _has_legacy_contexts(config_data: dict[str, Any]) -> bool:
    """True iff any context block is legacy-shaped (``api_url`` without ``url``).

    Post-migration blocks carry BOTH ``url`` and ``api_url`` (downgrade mirror),
    so they are NOT flagged legacy — keeps the no-op path correct.
    """
    return any(
        "api_url" in block and "url" not in block
        for block in _contexts_of(config_data).values()
    )


def _to_connection(block: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Normalize a legacy/registry block to a unified connection dict.

    Maps ``api_url→url`` / ``api_token→token``, drops ``default_app``, fills
    nothing it can't (missing optional fields are simply absent). Returns
    ``(unified, had_default_app)``.
    """
    url = block.get("url") or block.get("api_url") or ""
    token = block.get("token") or block.get("api_token") or ""
    unified: dict[str, Any] = {"url": str(url), "token": str(token)}
    for field in _CONNECTION_FIELDS:
        if field in block:
            unified[field] = block[field]
    return unified, bool(block.get("default_app"))


def _merge_prefer_token(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge two same-named connection blocks, preferring the token-bearing one."""
    if b.get("token") and not a.get("token"):
        return b
    if a.get("token") and not b.get("token"):
        return a
    # Both or neither have a token: later (servers.toml) wins, the newer source.
    return b


def _with_downgrade_mirror(block: dict[str, Any]) -> dict[str, Any]:
    """Add ``api_url``/``api_token`` alongside ``url``/``token`` for one release."""
    out = dict(block)
    out["api_url"] = block.get("url", "")
    out["api_token"] = block.get("token", "")
    return out


def _base_config(
    config_data: dict[str, Any],
    source_config: dict[str, Any],
    config_exists: bool,
) -> dict[str, Any]:
    """Start the new config from the right base, preserving non-context keys.

    Normal: start from the live config.toml (keeps theme/verbosity/etc.).
    Shape 3 (config.toml absent): recover preferences from the .pre-042.bak.
    Either way ``contexts`` is rebuilt by the caller, so drop it here.
    """
    base = dict(config_data) if config_exists else dict(source_config)
    base.pop("contexts", None)
    return base


def _backup_if_absent(src: Path, dst: Path) -> None:
    """Copy ``src`` → ``dst`` only if ``src`` exists and ``dst`` does not.

    Copy-if-absent so a resumed migration never overwrites the true original
    backup with an already-half-mutated file. ``copy2`` preserves mode/mtime.
    """
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
        _chmod_600(dst)


def _chmod_600(path: Path) -> None:
    """Best-effort 0o600 (these files hold a JWT token)."""
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
