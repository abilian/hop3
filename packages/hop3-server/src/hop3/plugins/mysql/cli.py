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
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register

_TYPE = "mysql"


def _result_items(result: dict) -> list[dict]:
    """Render a run_sql() result (rows or status) as response items.

    Cells are stringified so the payload is JSON-serializable over RPC
    (query results can contain dates, decimals, None, etc.).
    """
    if "columns" in result:
        rows = [
            ["" if cell is None else str(cell) for cell in row]
            for row in result["rows"]
        ]
        return [table(headers=result["columns"], rows=rows)]
    return [text(result["message"])]


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


@register
@dataclass(frozen=True)
class AddonMysqlQueryCmd(Command):
    """Run an ad-hoc SQL statement against a MySQL addon.

    Usage: hop3 addon mysql query <name> --command "<SQL>"

    Runs as the addon's own database user (least privilege), so it is confined
    to that addon's database. A SELECT returns a table; other statements report
    the affected row count.

    Examples:
        hop3 addon mysql query mydb --command "SELECT count(*) FROM orders"
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "query")
    _arg_spec: ClassVar[dict] = {
        "addon_name": {"positional": True},
        "command": {"type": str},
    }

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        statement = parsed.get("command")
        if not addon_name or not statement:
            return [text('Usage: hop3 addon mysql query <name> --command "<SQL>"')]
        with command_context(
            "running query", addon_name=addon_name, service_type=_TYPE
        ):
            result = get_addon(_TYPE, addon_name).run_sql(statement)
        return _result_items(result)


# --- Diagnostics (read-only, run as superuser via run_admin_sql) -------------

_PS_SQL = """
SELECT id, user, host, command, time, state, LEFT(info, 80) AS info
FROM information_schema.processlist
WHERE db = DATABASE()
ORDER BY time DESC
"""

_SETTINGS_SQL = """
SHOW GLOBAL VARIABLES WHERE Variable_name IN (
    'version', 'max_connections', 'innodb_buffer_pool_size',
    'max_allowed_packet', 'character_set_server', 'wait_timeout'
)
"""


def _diagnostic(args: tuple, statement: str, label: str, verb: str) -> list[dict]:
    """Shared body for the read-only diagnostic commands."""
    if not args:
        return [text(f"Usage: hop3 addon mysql {verb} <name>")]
    addon_name = args[0]
    with command_context(label, addon_name=addon_name, service_type=_TYPE):
        result = get_addon(_TYPE, addon_name).run_admin_sql(statement)
    return _result_items(result)


@register
@dataclass(frozen=True)
class AddonMysqlPsCmd(Command):
    """Show active queries on a MySQL addon.

    Usage: hop3 addon mysql ps <name>

    Examples:
        hop3 addon mysql ps mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "ps")

    def call(self, *args):
        return _diagnostic(args, _PS_SQL, "listing activity", "ps")


@register
@dataclass(frozen=True)
class AddonMysqlSettingsCmd(Command):
    """Show key configuration variables of a MySQL addon.

    Usage: hop3 addon mysql settings <name>

    Examples:
        hop3 addon mysql settings mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "settings")

    def call(self, *args):
        return _diagnostic(args, _SETTINGS_SQL, "reading settings", "settings")


# Contributed to the RPC dispatch table via MySQLPlugin.cli_commands().
COMMANDS: list[type[Command]] = [
    AddonMysqlCredentialsCmd,
    AddonMysqlDumpCmd,
    AddonMysqlRestoreCmd,
    AddonMysqlQueryCmd,
    AddonMysqlPsCmd,
    AddonMysqlSettingsCmd,
]
