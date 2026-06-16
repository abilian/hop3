# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""`addon mysql <verb>` commands — MySQL-specific addon management.

Type-agnostic addon verbs (list/create/attach/detach/destroy/show/status) live
in `hop3.commands.services`. These MySQL-specific level-3 commands are
contributed to the RPC dispatch table via the plugin's `cli_commands()` hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from hop3.commands._base import Command
from hop3.commands._errors import command_context
from hop3.commands._response import summary, table, text
from hop3.core.plugins import get_addon
from hop3.lib.decorators import register

_TYPE = "mysql"


@register
@dataclass(frozen=True)
class AddonMysqlCredentialsCmd(Command):
    """Show connection credentials for a MySQL addon.

    Usage: hop3 addon mysql credentials <name>

    Examples:
        hop3 addon mysql credentials mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "credentials")

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 addon mysql credentials <name>")]
        addon_name = args[0]
        with command_context(
            "reading addon credentials", addon_name=addon_name, service_type=_TYPE
        ):
            details = get_addon(_TYPE, addon_name).get_connection_details()
        rows = [[key, value] for key, value in details.items()]
        return [table(headers=["Variable", "Value"], rows=rows)]


@register
@dataclass(frozen=True)
class AddonMysqlDumpCmd(Command):
    """Dump a MySQL addon to a backup file (mysqldump).

    Usage: hop3 addon mysql dump <name>

    Examples:
        hop3 addon mysql dump mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "dump")

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 addon mysql dump <name>")]
        addon_name = args[0]
        with command_context(
            "dumping addon", addon_name=addon_name, service_type=_TYPE
        ):
            path = get_addon(_TYPE, addon_name).backup()
        return [
            text(f"Dumped MySQL addon '{addon_name}' to {path}."),
            summary(f"dumped addon '{addon_name}' ({_TYPE}) to {path}."),
        ]


@register
@dataclass(frozen=True)
class AddonMysqlRestoreCmd(Command):
    """Restore a MySQL addon from a backup file.

    Usage: hop3 addon mysql restore <name> <path>

    WARNING: overwrites the current contents of the database.

    Examples:
        hop3 addon mysql restore mydb /home/hop3/backups/mysql/mydb_2026.sql
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "restore")
    destructive: ClassVar[bool] = True

    def call(self, *args):
        if len(args) < 2:
            return [text("Usage: hop3 addon mysql restore <name> <path>")]
        addon_name, backup_path = args[0], args[1]
        with command_context(
            "restoring addon", addon_name=addon_name, service_type=_TYPE
        ):
            get_addon(_TYPE, addon_name).restore(Path(backup_path))
        return [
            text(f"Restored MySQL addon '{addon_name}' from {backup_path}."),
            summary(f"restored addon '{addon_name}' ({_TYPE}) from {backup_path}."),
        ]


# Contributed to the RPC dispatch table via MySQLPlugin.cli_commands().
COMMANDS: list[type[Command]] = [
    AddonMysqlCredentialsCmd,
    AddonMysqlDumpCmd,
    AddonMysqlRestoreCmd,
]
