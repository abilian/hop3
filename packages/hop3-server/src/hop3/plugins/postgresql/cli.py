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
from hop3.lib.decorators import register

_TYPE = "postgres"


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


# Contributed to the RPC dispatch table via PostgresqlPlugin.cli_commands().
COMMANDS: list[type[Command]] = [
    AddonPostgresCredentialsCmd,
    AddonPostgresDumpCmd,
    AddonPostgresRestoreCmd,
    AddonPostgresExtensionsCmd,
]
