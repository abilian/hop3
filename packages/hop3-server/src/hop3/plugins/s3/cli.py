# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""`addon s3 <verb>` commands — S3-specific addon management.

Type-agnostic addon verbs (list/create/attach/detach/destroy/show/status) live
in `hop3.commands.services`. These S3-specific level-3 commands are contributed
to the RPC dispatch table via the plugin's `cli_commands()` hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from hop3.commands._base import Command
from hop3.commands._errors import command_context
from hop3.commands._response import summary, table, text
from hop3.core.plugins import get_addon
from hop3.lib.decorators import register

_TYPE = "s3"


@register
@dataclass(frozen=True)
class AddonS3CredentialsCmd(Command):
    """Show connection credentials for an S3 addon.

    Usage: hop3 addon s3 credentials <name>

    Examples:
        hop3 addon s3 credentials mybucket
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "credentials")

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 addon s3 credentials <name>")]
        addon_name = args[0]
        with command_context(
            "reading addon credentials", addon_name=addon_name, service_type=_TYPE
        ):
            details = get_addon(_TYPE, addon_name).get_connection_details()
        rows = [[key, value] for key, value in details.items()]
        return [table(headers=["Variable", "Value"], rows=rows)]


@register
@dataclass(frozen=True)
class AddonS3DumpCmd(Command):
    """Dump an S3 addon's manifest (credentials + bucket metadata) to a file.

    Usage: hop3 addon s3 dump <name>

    Examples:
        hop3 addon s3 dump mybucket
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "dump")

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 addon s3 dump <name>")]
        addon_name = args[0]
        with command_context(
            "dumping addon", addon_name=addon_name, service_type=_TYPE
        ):
            path = get_addon(_TYPE, addon_name).backup()
        return [
            text(f"Dumped S3 addon '{addon_name}' manifest to {path}."),
            summary(f"dumped addon '{addon_name}' ({_TYPE}) to {path}."),
        ]


# Contributed to the RPC dispatch table via S3Plugin.cli_commands().
COMMANDS: list[type[Command]] = [
    AddonS3CredentialsCmd,
    AddonS3DumpCmd,
]
