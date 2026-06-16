# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""`addon postgres <verb>` commands — PostgreSQL-specific addon management.

Type-agnostic addon verbs (list/create/attach/detach/destroy/show/status) live
in `hop3.commands.services`. These are the Postgres-specific level-3 commands;
they are contributed to the RPC dispatch table via the plugin's `cli_commands()`
hook (see plugin.py).
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

_TYPE = "postgres"


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
class AddonPostgresCredentialsCmd(Command):
    """Show connection credentials for a Postgres addon.

    Usage: hop3 addon postgres credentials <name>

    Examples:
        hop3 addon postgres credentials mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "credentials")

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 addon postgres credentials <name>")]
        addon_name = args[0]
        with command_context(
            "reading addon credentials", addon_name=addon_name, service_type=_TYPE
        ):
            details = get_addon(_TYPE, addon_name).get_connection_details()
        rows = [[key, value] for key, value in details.items()]
        return [table(headers=["Variable", "Value"], rows=rows)]


@register
@dataclass(frozen=True)
class AddonPostgresDumpCmd(Command):
    """Dump a Postgres addon to a backup file (pg_dump).

    Usage: hop3 addon postgres dump <name>

    Examples:
        hop3 addon postgres dump mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "dump")

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 addon postgres dump <name>")]
        addon_name = args[0]
        with command_context(
            "dumping addon", addon_name=addon_name, service_type=_TYPE
        ):
            path = get_addon(_TYPE, addon_name).backup()
        return [
            text(f"Dumped Postgres addon '{addon_name}' to {path}."),
            summary(f"dumped addon '{addon_name}' ({_TYPE}) to {path}."),
        ]


@register
@dataclass(frozen=True)
class AddonPostgresRestoreCmd(Command):
    """Restore a Postgres addon from a backup file (psql).

    Usage: hop3 addon postgres restore <name> <path>

    WARNING: overwrites the current contents of the database.

    Examples:
        hop3 addon postgres restore mydb /home/hop3/backups/postgres/mydb_2026.sql
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "restore")
    destructive: ClassVar[bool] = True

    def call(self, *args):
        if len(args) < 2:
            return [text("Usage: hop3 addon postgres restore <name> <path>")]
        addon_name, backup_path = args[0], args[1]
        with command_context(
            "restoring addon", addon_name=addon_name, service_type=_TYPE
        ):
            get_addon(_TYPE, addon_name).restore(Path(backup_path))
        return [
            text(f"Restored Postgres addon '{addon_name}' from {backup_path}."),
            summary(f"restored addon '{addon_name}' ({_TYPE}) from {backup_path}."),
        ]


@register
@dataclass(frozen=True)
class AddonPostgresExtensionsCmd(Command):
    """Install PostgreSQL extensions into an addon's database.

    Usage: hop3 addon postgres extensions <name> <extension> [<extension> ...]

    Only extensions on the platform allow-list are installed (superuser-only
    extensions; trusted ones can be created from app migrations). See the
    addons guide for the allow-list and operator override.

    Examples:
        hop3 addon postgres extensions mydb postgis pgvector
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "extensions")

    def call(self, *args):
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
            get_addon(_TYPE, addon_name).install_extensions(list(extensions))
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
    """Run an ad-hoc SQL statement against a Postgres addon.

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

    def call(self, *args):
        parsed = parse_cli_args(args, self._arg_spec)
        addon_name = parsed.get("addon_name")
        statement = parsed.get("command")
        if not addon_name or not statement:
            return [text('Usage: hop3 addon postgres query <name> --command "<SQL>"')]
        with command_context(
            "running query", addon_name=addon_name, service_type=_TYPE
        ):
            result = get_addon(_TYPE, addon_name).run_sql(statement)
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
        result = get_addon(_TYPE, addon_name).run_admin_sql(statement)
    return _result_items(result)


@register
@dataclass(frozen=True)
class AddonPostgresPsCmd(Command):
    """Show active queries on a Postgres addon.

    Usage: hop3 addon postgres ps <name>

    Examples:
        hop3 addon postgres ps mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "ps")

    def call(self, *args):
        return _diagnostic(args, _PS_SQL, "listing activity", "ps")


@register
@dataclass(frozen=True)
class AddonPostgresLocksCmd(Command):
    """Show current locks on a Postgres addon.

    Usage: hop3 addon postgres locks <name>

    Examples:
        hop3 addon postgres locks mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "locks")

    def call(self, *args):
        return _diagnostic(args, _LOCKS_SQL, "listing locks", "locks")


@register
@dataclass(frozen=True)
class AddonPostgresSettingsCmd(Command):
    """Show key configuration settings of a Postgres addon.

    Usage: hop3 addon postgres settings <name>

    Examples:
        hop3 addon postgres settings mydb
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "settings")

    def call(self, *args):
        return _diagnostic(args, _SETTINGS_SQL, "reading settings", "settings")


# Contributed to the RPC dispatch table via PostgresqlPlugin.cli_commands().
COMMANDS: list[type[Command]] = [
    AddonPostgresCredentialsCmd,
    AddonPostgresDumpCmd,
    AddonPostgresRestoreCmd,
    AddonPostgresExtensionsCmd,
    AddonPostgresQueryCmd,
    AddonPostgresPsCmd,
    AddonPostgresLocksCmd,
    AddonPostgresSettingsCmd,
]
