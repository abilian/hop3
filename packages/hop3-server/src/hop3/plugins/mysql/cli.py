# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`addon mysql <verb>` commands — MySQL-specific addon management.

Type-agnostic addon verbs (list/create/attach/detach/destroy/show/status) live
in `hop3.commands.services`. These MySQL-specific level-3 commands are
contributed to the RPC dispatch table via the plugin's `cli_commands()` hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, cast

from hop3.commands._base import Command, NamespaceCommand
from hop3.commands._errors import command_context
from hop3.commands._response import table, text
from hop3.core.plugins import get_addon
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register
from hop3.plugins.addons.generic_cli import (
    AddonCliSpec,
    generic_addon_commands,
)

if TYPE_CHECKING:
    from .mysql import MySQLAddon

_TYPE = "mysql"

_GENERIC = AddonCliSpec(
    type_name=_TYPE,
    label="MySQL",
    example="mydb",
    dump_suffix=".sql",
    dump_filename="dump.sql",
    dump_tool="mysqldump",
    restore_tool="the mysql client",
    restore_target="the current contents of the database",
    clone_example=("prod-db", "staging-db"),
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


def _addon(name: str) -> MySQLAddon:
    """Typed accessor for the concrete MySQL addon (engine-specific methods)."""
    return cast("MySQLAddon", get_addon(_TYPE, name))


def _result_items(result: dict) -> list[dict]:
    """
    Render a run_sql() result (rows or status) as response items.

    Cells are stringified so the payload is JSON-serializable over RPC
    (query results can contain dates, decimals, None, etc.).
    """
    if "columns" in result:
        rows = [
            ["" if cell is None else str(cell) for cell in row]
            for row in result["rows"]
        ]
        return [table(headers=result["columns"], rows=rows)]
    if "message" in result:
        return [text(result["message"])]
    msg = f"unexpected run_sql result shape: {result!r}"
    raise ValueError(msg)


@register
@dataclass(frozen=True)
class AddonMysqlQueryCmd(Command):
    """
    Run an ad-hoc SQL statement against a MySQL addon.

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

    def call(self, *args: str) -> list[dict]:
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        statement = parsed.get("command")
        if not addon_name or not statement:
            return [text('Usage: hop3 addon mysql query <name> --command "<SQL>"')]
        with command_context(
            "running query", addon_name=addon_name, service_type=_TYPE
        ):
            result = _addon(addon_name).run_sql(statement)
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
        result = _addon(addon_name).run_admin_sql(statement)
    return _result_items(result)


@register
@dataclass(frozen=True)
class AddonMysqlPsCmd(Command):
    """
    Show active queries on a MySQL addon.

    Usage: hop3 addon mysql activity <name>

    Examples:
        hop3 addon mysql activity mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "activity")
    aliases: ClassVar[list[tuple[str, ...]]] = [("addon", _TYPE, "ps")]

    def call(self, *args: str) -> list[dict]:
        return _diagnostic(args, _PS_SQL, "listing activity", "activity")


@register
@dataclass(frozen=True)
class AddonMysqlSettingsCmd(Command):
    """
    Show key configuration variables of a MySQL addon.

    Usage: hop3 addon mysql settings <name>

    Examples:
        hop3 addon mysql settings mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "settings")

    def call(self, *args: str) -> list[dict]:
        return _diagnostic(args, _SETTINGS_SQL, "reading settings", "settings")


# Contributed to the RPC dispatch table via MySQLPlugin.cli_commands().
@register
class AddonMysqlCmd(NamespaceCommand):
    """
    MySQL addon operations: backup, restore, query, clone, and more.

    Work with one MySQL instance: show its credentials, dump/restore its data,
    run ad-hoc SQL, inspect activity, or clone it. Create an instance with
    'hop3 addon create mysql <name>'.

    Examples:
        hop3 addon mysql credentials mydb               # Connection details
        hop3 addon mysql dump mydb                       # Back up (mysqldump)
        hop3 addon mysql query mydb --command "SELECT 1"
        hop3 addon mysql clone mydb mydb-copy            # Copy all data
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE)


COMMANDS: list[type[Command]] = [
    *_GENERIC_COMMANDS,
    AddonMysqlCmd,
    AddonMysqlQueryCmd,
    AddonMysqlPsCmd,
    AddonMysqlSettingsCmd,
]
