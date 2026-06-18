# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""`addon s3 <verb>` commands — S3-specific addon management.

Type-agnostic addon verbs (list/create/attach/detach/destroy/show/status) live
in `hop3.commands.services`. These S3-specific level-3 commands are contributed
to the RPC dispatch table via the plugin's `cli_commands()` hook.
"""

from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from hop3.commands._base import Command
from hop3.commands._errors import command_context
from hop3.commands._response import blob, error, summary, table, text
from hop3.core.identifiers import InvalidIdentifierError, validate_service_name
from hop3.core.plugins import get_addon
from hop3.lib.decorators import register

_TYPE = "s3"


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


@register
@dataclass(frozen=True)
class AddonS3RestoreCmd(Command):
    """Restore an S3 addon from a dump file.

    Usage: hop3 addon s3 restore <name> <path>

    WARNING: overwrites the addon's current bucket contents / manifest.

    Examples:
        hop3 addon s3 restore mybucket /home/hop3/backups/s3/mybucket.dump
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "restore")
    destructive: ClassVar[bool] = True

    def call(self, *args):
        if len(args) < 2:
            return [text("Usage: hop3 addon s3 restore <name> <path>")]
        addon_name, backup_path = args[0], args[1]
        with command_context(
            "restoring addon", addon_name=addon_name, service_type=_TYPE
        ):
            get_addon(_TYPE, addon_name).restore(Path(backup_path))
        return [
            text(f"Restored S3 addon '{addon_name}' from {backup_path}."),
            summary(f"restored addon '{addon_name}' ({_TYPE}) from {backup_path}."),
        ]


@register
@dataclass(frozen=True)
class AddonS3CloneCmd(Command):
    """Clone an S3 addon into a new one (copies its data).

    Usage: hop3 addon s3 clone <source> <new-name>

    Creates <new-name>, then loads a dump of <source> into it. Refuses if
    <new-name> already exists.

    Examples:
        hop3 addon s3 clone prod-bucket staging-bucket
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "clone")

    def call(self, *args):
        return _clone(args)


@register
@dataclass(frozen=True)
class AddonS3ExportCmd(Command):
    """Stream an S3 addon dump to stdout.

    Usage: hop3 addon s3 export <name> > dump
    Writes the addon's dump (manifest + bucket data) to the client's stdout —
    redirect it to a file or pipe it elsewhere.

    Examples:
        hop3 addon s3 export mybucket > mybucket.dump
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "export")

    def call(self, *args):
        if not args:
            return [text("Usage: hop3 addon s3 export <name> > dump")]
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
class AddonS3ImportCmd(Command):
    """Import a dump into an S3 addon from stdin.

    Usage: hop3 addon s3 import <name> --confirm=<name> < dump

    Loads the piped dump into the addon. Overwrites existing data; since stdin
    carries the dump (so it can't prompt), pass --confirm=<name> or --yes.

    Examples:
        hop3 addon s3 import mybucket --confirm=mybucket < mybucket.dump
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE, "import")
    destructive: ClassVar[bool] = True

    def call(self, *args, import_data: str | None = None, **kwargs):
        if not args:
            return [text("Usage: hop3 addon s3 import <name> < dump")]
        addon_name = args[0]
        if not import_data:
            return [
                error(
                    "No dump provided. Pipe one on stdin: "
                    "hop3 addon s3 import <name> < dump"
                )
            ]
        with command_context(
            "importing addon", addon_name=addon_name, service_type=_TYPE
        ):
            content = base64.b64decode(import_data)
            with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
            try:
                get_addon(_TYPE, addon_name).restore(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
        return [
            text(f"Imported dump into S3 addon '{addon_name}'."),
            summary(f"imported dump into addon '{addon_name}' ({_TYPE})."),
        ]


# Contributed to the RPC dispatch table via S3Plugin.cli_commands().
COMMANDS: list[type[Command]] = [
    AddonS3CredentialsCmd,
    AddonS3DumpCmd,
    AddonS3RestoreCmd,
    AddonS3CloneCmd,
    AddonS3ExportCmd,
    AddonS3ImportCmd,
]
