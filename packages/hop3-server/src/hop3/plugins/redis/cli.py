# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""`addon redis <verb>` commands — Redis-specific addon management.

Type-agnostic addon verbs (list/create/attach/detach/destroy/show/status) live
in `hop3.commands.services`. These Redis-specific level-3 commands are
contributed to the RPC dispatch table via the plugin's `cli_commands()` hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, cast

from hop3.commands._base import Command
from hop3.commands._errors import command_context
from hop3.commands._response import summary, table, text
from hop3.core.plugins import get_addon
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register

if TYPE_CHECKING:
    from .redis import RedisAddon

_TYPE = "redis"


def _addon(name: str) -> RedisAddon:
    """Typed accessor for the concrete Redis addon (engine-specific methods)."""
    return cast("RedisAddon", get_addon(_TYPE, name))


@register
@dataclass(frozen=True)
class AddonRedisCredentialsCmd(Command):
    """Show connection credentials for a Redis addon.

    Usage: hop3 addon redis credentials <name>

    Examples:
        hop3 addon redis credentials mycache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "credentials")

    def call(self, *args):
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
    """Dump a Redis addon's keys to a backup file.

    Usage: hop3 addon redis dump <name>

    Examples:
        hop3 addon redis dump mycache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "dump")

    def call(self, *args):
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
    """Remove all keys from a Redis addon's database (FLUSHDB).

    Usage: hop3 addon redis flush <name>

    WARNING: deletes every key in the addon's database. The addon itself
    stays usable (its db assignment is kept).

    Examples:
        hop3 addon redis flush mycache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "flush")
    destructive: ClassVar[bool] = True

    def call(self, *args):
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
    """Run an ad-hoc redis-cli command against a Redis addon.

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

    def call(self, *args):
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
    """Show Redis server INFO for a Redis addon (diagnostics).

    Usage: hop3 addon redis info <name>

    Examples:
        hop3 addon redis info mycache
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "info")

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 addon redis info <name>")]
        addon_name = args[0]
        with command_context("reading info", addon_name=addon_name, service_type=_TYPE):
            output = _addon(addon_name).run_command("INFO")
        return [text(output or "(empty)")]


# Contributed to the RPC dispatch table via RedisPlugin.cli_commands().
COMMANDS: list[type[Command]] = [
    AddonRedisCredentialsCmd,
    AddonRedisDumpCmd,
    AddonRedisFlushCmd,
    AddonRedisQueryCmd,
    AddonRedisInfoCmd,
]
