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

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, cast

from hop3.commands._base import Command, NamespaceCommand
from hop3.commands._errors import command_context
from hop3.commands._response import summary, text
from hop3.core.plugins import get_addon
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register
from hop3.plugins.addons.generic_cli import (
    AddonCliSpec,
    generic_addon_commands,
)

if TYPE_CHECKING:
    from .redis import RedisAddon

_TYPE = "redis"

_GENERIC = AddonCliSpec(
    type_name=_TYPE,
    label="Redis",
    example="mycache",
    dump_suffix=".rdb",
    dump_filename="dump.rdb",
    dump_contents="keys",
    restore_target="the current contents of the addon's database",
    clone_example=("prod-cache", "staging-cache"),
)

#: credentials / dump / restore / clone / export / import — identical
#: for every addon type, so they are built from the spec above rather
#: than written out a fourth time. Engine-specific verbs stay below.
_GENERIC_COMMANDS = generic_addon_commands(_GENERIC)
for _cmd in _GENERIC_COMMANDS:
    register(_cmd)
    # Bind each generated class under the name it had when it was written out
    # by hand (AddonRedisExportCmd, ...), so this is a drop-in replacement:
    # anything importing one by name — the existing unit tests included —
    # keeps working, and those tests keep testing the real command.
    globals()[_cmd.__name__] = _cmd


def _addon(name: str) -> RedisAddon:
    """Typed accessor for the concrete Redis addon (engine-specific methods)."""
    return cast("RedisAddon", get_addon(_TYPE, name))


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
    *_GENERIC_COMMANDS,
    AddonRedisCmd,
    AddonRedisFlushCmd,
    AddonRedisQueryCmd,
    AddonRedisInfoCmd,
]
