# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Third ADR-042 migration: every target is a **named** context.

Two records could name the connection, and they resolved at different ranks:

- ``[cli].default_server`` is an *unnamed* default target that
  ``Config.get_api_url`` consults BELOW every context. An operator with any
  context at all was therefore unaffected by it — ``hop3 login`` wrote it and
  ``hop3 apps`` ignored it, while the login reported success.
- "Which context is current" had two keys, ``[cli].current_context`` and
  ``[cli].default_context``, read by two functions that disagreed. Stage 2
  drains the former, but only for a config that already has ``[contexts.*]``;
  one without them was left with the stale pointer.

After this stage there is one of each: every target is a named context, and
``[cli].default_context`` names the current one.

Crash-safety, the same contract as stages 1 and 2:

- **Abort loud / change nothing** on a malformed ``config.toml``, and on the one
  ambiguous shape this cannot resolve (see ``_name_for_default_server``).
- **Copy-if-absent backup** before any write.
- **Idempotent**: once there is no ``default_server`` and no stale pointer, a
  no-op with zero disk writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hop3_cli.config import DEFAULT_CONTEXT_NAME
from hop3_cli.core.config_migration_v2 import (
    CONFIG_FILENAME,
    MigrationError,
    as_text,
    chmod_600,
    load_or_abort,
)
from hop3_cli.core.local_overlay import atomic_write_toml

if TYPE_CHECKING:
    from pathlib import Path

BACKUP_SUFFIX = ".pre-named-target.bak"


def migrate_to_named_targets(config_dir: Path) -> list[str]:
    """
    Give the unnamed default target a name, and settle one current-context key.

    Returns human-readable notes (empty on the no-op path). Raises
    ``MigrationError`` — nothing changed on disk — on malformed input.
    """
    config_path = config_dir / CONFIG_FILENAME
    if not config_path.is_file():
        return []

    data = load_or_abort(config_path)
    cli = data.get("cli")
    cli = dict(cli) if isinstance(cli, dict) else {}

    default_server = as_text(cli.get("default_server"))
    pointer = _legacy_pointer(data)
    if not default_server and not pointer:
        return []  # no-op: nothing unnamed, no stale pointer

    contexts = data.get("contexts")
    contexts = dict(contexts) if isinstance(contexts, dict) else {}
    current = as_text(cli.get("default_context"))
    notes: list[str] = []

    # The legacy pointer, but only when it names a context that exists and
    # nothing already claims to be current — never override a live choice.
    # Every other outcome drops it, and says so: a pointer that quietly stops
    # existing is the kind of silent change this migration is here to end.
    if pointer:
        if pointer not in contexts:
            notes.append(
                f"Dropped [cli].current_context = {pointer!r}: no context has "
                f"that name."
            )
        elif not current:
            current = pointer
            notes.append(f"Current context: {pointer!r} (was [cli].current_context).")
        elif current != pointer:
            notes.append(
                f"Dropped [cli].current_context = {pointer!r}; "
                f"[cli].default_context = {current!r} was already in effect."
            )

    if default_server:
        name = _name_for_default_server(contexts, default_server, current=current)
        if name is None:
            notes.append(
                f"Dropped the unreachable [cli].default_server "
                f"({default_server}): context {current!r} outranks it."
            )
        elif name in contexts:
            notes.append(
                f"Dropped [cli].default_server: context {name!r} already "
                f"names {default_server}."
            )
            current = current or name
        else:
            contexts[name] = {"server": default_server}
            notes.append(f"Named {default_server} as context {name!r}.")
            current = current or name

    _write(config_path, data, contexts, cli, current)
    return notes


def _name_for_default_server(
    contexts: dict[str, Any], address: str, *, current: str | None
) -> str | None:
    """
    Which context should hold the unnamed default server.

    An existing context with that address, else ``default`` when it is free.
    ``None`` means the address was already unreachable and is dropped: a context
    is current, and every context outranks ``default_server``.
    """
    for name in sorted(contexts):
        block = contexts[name]
        if isinstance(block, dict) and as_text(block.get("server")) == address:
            return name

    if DEFAULT_CONTEXT_NAME not in contexts:
        return DEFAULT_CONTEXT_NAME

    if current:
        return None  # dead weight: a named context is current and outranks it

    # `default` names a different server, nothing is current, and this address
    # is the one commands actually reach. Guessing another name would invent a
    # target; overwriting `default` would silently retarget the other one.
    held = contexts[DEFAULT_CONTEXT_NAME]
    other = as_text(held.get("server")) if isinstance(held, dict) else "?"
    msg = (
        f"config.toml is ambiguous: [cli].default_server is {address} while "
        f"[contexts.{DEFAULT_CONTEXT_NAME}] names {other}, and no context is "
        f"current. Nothing was changed. Set [cli].default_context to the one "
        f"you mean, or remove [cli].default_server."
    )
    raise MigrationError(msg)


def _write(
    config_path: Path,
    data: dict[str, Any],
    contexts: dict[str, Any],
    cli: dict[str, Any],
    current: str | None,
) -> None:
    """Back up, then rewrite with one target model. Nothing is written before the backup."""
    backup = config_path.with_name(config_path.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(config_path.read_bytes())
        chmod_600(backup)

    cli.pop("default_server", None)
    cli.pop("current_context", None)
    if current:
        cli["default_context"] = current
    else:
        cli.pop("default_context", None)

    new_config = {
        k: v for k, v in data.items() if k not in {"contexts", "current_context", "cli"}
    }
    if contexts:
        new_config["contexts"] = contexts
    if cli:
        new_config["cli"] = cli

    atomic_write_toml(config_path, new_config)
    chmod_600(config_path)


def _legacy_pointer(data: dict[str, Any]) -> str | None:
    """The old current-context pointer (``[cli].current_context`` or top-level)."""
    cli = data.get("cli")
    if isinstance(cli, dict) and as_text(cli.get("current_context")):
        return as_text(cli["current_context"])
    return as_text(data.get("current_context"))
