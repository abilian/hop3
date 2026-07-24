# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`addon redis <verb>` commands — Redis-specific addon management.

Type-agnostic addon verbs (list/create/attach/detach/destroy/show/status) live
in `hop3.commands.services`. These Redis-specific level-3 commands are
contributed to the RPC dispatch table via the plugin's `cli_commands()` hook.
"""

from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, cast

from hop3.commands._base import Command, NamespaceCommand
from hop3.commands._errors import command_context
from hop3.commands._response import blob, error, summary, table, text
from hop3.core.identifiers import InvalidIdentifierError, validate_service_name
from hop3.core.plugins import get_addon
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register

if TYPE_CHECKING:
    from .redis import RedisAddon

_TYPE = "redis"


def _addon(name: str) -> RedisAddon:
    """Typed accessor for the concrete Redis addon (engine-specific methods)."""
    return cast("RedisAddon", get_addon(_TYPE, name))


def _clone(args: tuple) -> list[dict]:
    """Create a new addon and copy the source addon's data into it."""
    if len(args) < 2:
        return [text(f"Usage: hop3 addon {_TYPE} clone <source> <new-name>")]
    source, target = args[0], args[1]
    try:
        validate_service_name(target)
    except InvalidIdentifierError as exc:
        return [error(str(exc))]
    with command_context("cloning addon", addon_name=source, service_type=_TYPE):
        dst = get_addon(_TYPE, target)
        if hasattr(dst, "exists") and dst.exists():
            return [error(f"Addon '{target}' already exists.")]
        dst.create()
        dst.restore(get_addon(_TYPE, source).backup())
    return [
        text(f"Cloned {_TYPE} addon '{source}' into '{target}'."),
        summary(f"cloned addon '{source}' -> '{target}' ({_TYPE})."),
    ]


@register
@dataclass(frozen=True)
class AddonRedisCredentialsCmd(Command):
    """
    Show connection credentials for a Redis addon.

    Usage: hop3 addon redis credentials <name>

    Examples:
        hop3 addon redis credentials mycache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "credentials")

    def call(self, *args: str) -> list[dict]:
        if not args:
            return [text("Usage: hop3 addon redis credentials <name>")]
        addon_name = args[0]
        with command_context(
            "reading addon credentials", addon_name=addon_name, service_type=_TYPE
        ):
            details = get_addon(_TYPE, addon_name).get_connection_details()
        rows = [[key, value] for key, value in details.items()]
        return [table(headers=["Variable", "Value"], rows=rows)]


@register
@dataclass(frozen=True)
class AddonRedisDumpCmd(Command):
    """
    Dump a Redis addon's keys to a backup file.

    Usage: hop3 addon redis dump <name>

    Examples:
        hop3 addon redis dump mycache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "dump")

    def call(self, *args: str) -> list[dict]:
        if not args:
            return [text("Usage: hop3 addon redis dump <name>")]
        addon_name = args[0]
        with command_context(
            "dumping addon", addon_name=addon_name, service_type=_TYPE
        ):
            path = get_addon(_TYPE, addon_name).backup()
        return [
            text(f"Dumped Redis addon '{addon_name}' to {path}."),
            summary(f"dumped addon '{addon_name}' ({_TYPE}) to {path}."),
        ]


@register
@dataclass(frozen=True)
class AddonRedisFlushCmd(Command):
    """
    Remove all keys from a Redis addon's database (FLUSHDB).

    Usage: hop3 addon redis flush <name>

    WARNING: deletes every key in the addon's database. The addon itself
    stays usable (its db assignment is kept).

    Examples:
        hop3 addon redis flush mycache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "flush")
    destructive: ClassVar[bool] = True

    def call(self, *args: str) -> list[dict]:
        if not args:
            return [text("Usage: hop3 addon redis flush <name>")]
        addon_name = args[0]
        with command_context(
            "flushing addon", addon_name=addon_name, service_type=_TYPE
        ):
            _addon(addon_name).flush()
        return [
            text(f"Flushed all keys from Redis addon '{addon_name}'."),
            summary(f"flushed addon '{addon_name}' ({_TYPE})."),
        ]


@register
@dataclass(frozen=True)
class AddonRedisQueryCmd(Command):
    """
    Run an ad-hoc redis-cli command against a Redis addon.

    Usage: hop3 addon redis query <name> --command "<redis command>"

    The command runs scoped to the addon's own database (not db 0).

    Examples:
        hop3 addon redis query mycache --command "GET session:42"
        hop3 addon redis query mycache --command "DBSIZE"
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "query")
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "command": {"type": str},
    }

    def call(self, *args: str) -> list[dict]:
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        command = parsed.get("command")
        if not addon_name or not command:
            return [
                text('Usage: hop3 addon redis query <name> --command "<redis command>"')
            ]
        with command_context(
            "running command", addon_name=addon_name, service_type=_TYPE
        ):
            output = _addon(addon_name).run_command(command)
        return [text(output or "(empty)")]


@register
@dataclass(frozen=True)
class AddonRedisInfoCmd(Command):
    """
    Show Redis server INFO for a Redis addon (diagnostics).

    Usage: hop3 addon redis info <name>

    Examples:
        hop3 addon redis info mycache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "info")

    def call(self, *args: str) -> list[dict]:
        if not args:
            return [text("Usage: hop3 addon redis info <name>")]
        addon_name = args[0]
        with command_context("reading info", addon_name=addon_name, service_type=_TYPE):
            output = _addon(addon_name).run_command("INFO")
        return [text(output or "(empty)")]


@register
@dataclass(frozen=True)
class AddonRedisRestoreCmd(Command):
    """
    Restore a Redis addon from a dump file.

    Usage: hop3 addon redis restore <name> <path>

    WARNING: overwrites the current contents of the addon's database.

    Examples:
        hop3 addon redis restore mycache /home/hop3/backups/redis/mycache.rdb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "restore")
    destructive: ClassVar[bool] = True

    def call(self, *args: str) -> list[dict]:
        if len(args) < 2:
            return [text("Usage: hop3 addon redis restore <name> <path>")]
        addon_name, backup_path = args[0], args[1]
        with command_context(
            "restoring addon", addon_name=addon_name, service_type=_TYPE
        ):
            get_addon(_TYPE, addon_name).restore(Path(backup_path))
        return [
            text(f"Restored Redis addon '{addon_name}' from {backup_path}."),
            summary(f"restored addon '{addon_name}' ({_TYPE}) from {backup_path}."),
        ]


@register
@dataclass(frozen=True)
class AddonRedisCloneCmd(Command):
    """
    Clone a Redis addon into a new one (copies all data).

    Usage: hop3 addon redis clone <source> <new-name>

    Creates <new-name>, then loads a dump of <source> into it. Refuses if
    <new-name> already exists.

    Examples:
        hop3 addon redis clone prod-cache staging-cache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "clone")

    def call(self, *args: str) -> list[dict]:
        return _clone(args)


@register
@dataclass(frozen=True)
class AddonRedisExportCmd(Command):
    """
    Stream a Redis addon dump to stdout.

    Usage: hop3 addon redis export <name> > dump.rdb

    Writes the addon's dump to the client's stdout — redirect it to a file or
    pipe it elsewhere.

    Examples:
        hop3 addon redis export mycache > mycache.rdb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "export")

    def call(self, *args: str) -> list[dict]:
        if not args:
            return [text("Usage: hop3 addon redis export <name> > dump.rdb")]
        addon_name = args[0]
        with command_context(
            "exporting addon", addon_name=addon_name, service_type=_TYPE
        ):
            path = Path(get_addon(_TYPE, addon_name).backup())
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return [
            blob(encoded, filename=path.name),
            summary(f"exported addon '{addon_name}' ({_TYPE})."),
        ]


@register
@dataclass(frozen=True)
class AddonRedisImportCmd(Command):
    """
    Import a dump into a Redis addon from stdin.

    Usage: hop3 addon redis import <name> --confirm=<name> < dump.rdb

    Loads the piped dump into the addon. Overwrites existing data; since stdin
    carries the dump (so it can't prompt), pass --confirm=<name> or --yes.

    Examples:
        hop3 addon redis import mycache --confirm=mycache < mycache.rdb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "import")
    destructive: ClassVar[bool] = True

    def call(
        self, *args: str, import_data: str | None = None, **kwargs: object
    ) -> list[dict]:
        if not args:
            return [text("Usage: hop3 addon redis import <name> < dump.rdb")]
        addon_name = args[0]
        if not import_data:
            return [
                error(
                    "No dump provided. Pipe one on stdin: "
                    "hop3 addon redis import <name> < dump.rdb"
                )
            ]
        with command_context(
            "importing addon", addon_name=addon_name, service_type=_TYPE
        ):
            content = base64.b64decode(import_data)
            with tempfile.NamedTemporaryFile(suffix=".rdb", delete=False) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
            try:
                get_addon(_TYPE, addon_name).restore(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
        return [
            text(f"Imported dump into Redis addon '{addon_name}'."),
            summary(f"imported dump into addon '{addon_name}' ({_TYPE})."),
        ]


# Contributed to the RPC dispatch table via RedisPlugin.cli_commands().
@register
class AddonRedisCmd(NamespaceCommand):
    """
    Redis addon operations: dump, restore, query, flush, and diagnostics.

    Work with one Redis instance: show its credentials, dump/restore its keys,
    run redis-cli commands, flush its database, or read server INFO. Create an
    instance with 'hop3 addon create redis <name>'.

    Examples:
        hop3 addon redis credentials mycache            # Connection details
        hop3 addon redis dump mycache                    # Back up its keys
        hop3 addon redis query mycache PING              # Ad-hoc redis-cli
        hop3 addon redis info mycache                    # Server INFO
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE)


COMMANDS: list[type[Command]] = [
    AddonRedisCmd,
    AddonRedisCredentialsCmd,
    AddonRedisDumpCmd,
    AddonRedisRestoreCmd,
    AddonRedisFlushCmd,
    AddonRedisQueryCmd,
    AddonRedisCloneCmd,
    AddonRedisExportCmd,
    AddonRedisImportCmd,
    AddonRedisInfoCmd,
]
