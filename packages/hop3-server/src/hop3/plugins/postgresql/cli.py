# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`addon postgres <verb>` commands — PostgreSQL-specific addon management.

Type-agnostic addon verbs (list/create/attach/detach/destroy/show/status) live
in `hop3.commands.services`. These are the Postgres-specific level-3 commands;
they are contributed to the RPC dispatch table via the plugin's `cli_commands()`
hook (see plugin.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, cast

from hop3.commands._base import Command, NamespaceCommand
from hop3.commands._errors import command_context
from hop3.commands._response import summary, table, text
from hop3.core.plugins import get_addon
from hop3.lib.args import parse_cli_args
from hop3.lib.decorators import register
from hop3.plugins.addons.generic_cli import (
    AddonCliSpec,
    generic_addon_commands,
)

if TYPE_CHECKING:
    from .postgres import PostgresAddon

_TYPE = "postgres"

_GENERIC = AddonCliSpec(
    type_name=_TYPE,
    label="PostgreSQL",
    example="mydb",
    dump_suffix=".sql",
    dump_filename="dump.sql",
    dump_tool="pg_dump",
    restore_tool="psql",
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


def _addon(name: str) -> PostgresAddon:
    """Typed accessor for the concrete Postgres addon (engine-specific methods)."""
    return cast("PostgresAddon", get_addon(_TYPE, name))


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
class AddonPostgresExtensionsCmd(Command):
    """
    Install PostgreSQL extensions into an addon's database.

    Usage: hop3 addon postgres extensions <name> <extension> [<extension> ...]

    Only extensions on the platform allow-list are installed (superuser-only
    extensions; trusted ones can be created from app migrations). See the
    addons guide for the allow-list and operator override.

    Examples:
        hop3 addon postgres extensions mydb postgis pgvector
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "extensions")

    def call(self, *args: str) -> list[dict]:
        if len(args) < 2:
            return [
                text(
                    "Usage: hop3 addon postgres extensions <name> "
                    "<extension> [<extension> ...]"
                )
            ]
        addon_name, *extensions = args
        with command_context(
            "installing extensions",
            addon_name=addon_name,
            service_type=_TYPE,
            extensions=",".join(extensions),
        ):
            _addon(addon_name).install_extensions(list(extensions))
        return [
            text(
                f"Installed extension(s) {', '.join(extensions)} "
                f"into Postgres addon '{addon_name}'."
            ),
            summary(
                f"installed extensions [{', '.join(extensions)}] "
                f"on addon '{addon_name}' ({_TYPE})."
            ),
        ]


@register
@dataclass(frozen=True)
class AddonPostgresQueryCmd(Command):
    """
    Run an ad-hoc SQL statement against a Postgres addon.

    Usage: hop3 addon postgres query <name> --command "<SQL>"

    Runs as the addon's own database user (least privilege), so it is confined
    to that addon's database. A SELECT returns a table; other statements report
    the affected row count.

    Examples:
        hop3 addon postgres query mydb --command "SELECT count(*) FROM users"
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
            return [text('Usage: hop3 addon postgres query <name> --command "<SQL>"')]
        with command_context(
            "running query", addon_name=addon_name, service_type=_TYPE
        ):
            result = _addon(addon_name).run_sql(statement)
        return _result_items(result)


# --- Diagnostics (read-only, run as superuser via run_admin_sql) -------------

_PS_SQL = r"""
SELECT pid,
       usename AS "user",
       state,
       to_char(now() - query_start, 'HH24:MI:SS') AS runtime,
       left(regexp_replace(query, '\s+', ' ', 'g'), 80) AS query
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND state IS NOT NULL
ORDER BY query_start NULLS LAST
"""

_LOCKS_SQL = r"""
SELECT a.pid,
       a.usename AS "user",
       l.locktype,
       l.mode,
       l.granted,
       left(regexp_replace(a.query, '\s+', ' ', 'g'), 60) AS query
FROM pg_locks l
JOIN pg_stat_activity a ON a.pid = l.pid
WHERE a.datname = current_database()
ORDER BY l.granted, a.pid
"""

_SETTINGS_SQL = r"""
SELECT name, setting, unit
FROM pg_settings
WHERE name IN (
    'server_version', 'max_connections', 'shared_buffers', 'work_mem',
    'maintenance_work_mem', 'effective_cache_size', 'wal_level', 'max_wal_size'
)
ORDER BY name
"""


def _diagnostic(args: tuple, statement: str, label: str, verb: str) -> list[dict]:
    """Shared body for the read-only diagnostic commands."""
    if not args:
        return [text(f"Usage: hop3 addon postgres {verb} <name>")]
    addon_name = args[0]
    with command_context(label, addon_name=addon_name, service_type=_TYPE):
        result = _addon(addon_name).run_admin_sql(statement)
    return _result_items(result)


@register
@dataclass(frozen=True)
class AddonPostgresPsCmd(Command):
    """
    Show active queries on a Postgres addon.

    Usage: hop3 addon postgres activity <name>

    Examples:
        hop3 addon postgres activity mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "activity")
    aliases: ClassVar[list[tuple[str, ...]]] = [("addon", _TYPE, "ps")]

    def call(self, *args: str) -> list[dict]:
        return _diagnostic(args, _PS_SQL, "listing activity", "activity")


@register
@dataclass(frozen=True)
class AddonPostgresLocksCmd(Command):
    """
    Show current locks on a Postgres addon.

    Usage: hop3 addon postgres locks <name>

    Examples:
        hop3 addon postgres locks mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "locks")

    def call(self, *args: str) -> list[dict]:
        return _diagnostic(args, _LOCKS_SQL, "listing locks", "locks")


@register
@dataclass(frozen=True)
class AddonPostgresSettingsCmd(Command):
    """
    Show key configuration settings of a Postgres addon.

    Usage: hop3 addon postgres settings <name>

    Examples:
        hop3 addon postgres settings mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "settings")

    def call(self, *args: str) -> list[dict]:
        return _diagnostic(args, _SETTINGS_SQL, "reading settings", "settings")


# Contributed to the RPC dispatch table via PostgresqlPlugin.cli_commands().
@register
class AddonPostgresCmd(NamespaceCommand):
    """
    PostgreSQL addon operations: backup, restore, query, clone, and more.

    Work with one Postgres instance: show its credentials, dump/restore its
    data, run ad-hoc SQL, inspect locks and activity, or install extensions.
    Create an instance with 'hop3 addon create postgres <name>'.

    Examples:
        hop3 addon postgres credentials mydb            # Connection details
        hop3 addon postgres dump mydb                   # Back up (pg_dump)
        hop3 addon postgres query mydb --command "SELECT 1"
        hop3 addon postgres clone mydb mydb-copy        # Copy all data
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE)


COMMANDS: list[type[Command]] = [
    *_GENERIC_COMMANDS,
    AddonPostgresCmd,
    AddonPostgresExtensionsCmd,
    AddonPostgresQueryCmd,
    AddonPostgresPsCmd,
    AddonPostgresLocksCmd,
    AddonPostgresSettingsCmd,
]
