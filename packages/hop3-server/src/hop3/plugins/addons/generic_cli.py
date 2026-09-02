# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The addon CLI verbs every backing service shares, generated once.

``credentials``, ``dump``, ``restore``, ``clone``, ``export`` and ``import``
mean the same thing for PostgreSQL, MySQL, Redis and S3, and were written out
four times: 24 command classes across four files whose bodies were identical
once the type name was substituted, differing only in which tool the docstring
named. A fix or a new option therefore had to be applied four times, and the
fourth was the one that got forgotten.

Engine-specific verbs stay in their own plugin — ``postgres extensions``,
``redis flush``, ``mysql settings`` and the rest are genuinely different
commands, not four spellings of one.

:class:`AddonCliSpec` carries everything that legitimately varies (the type
name, how the service is written in prose, the dump file's extension, the
tools named in help text) and :func:`generic_addon_commands` returns the
command classes for one addon type, ready to register.
"""

from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hop3.commands._base import Command
from hop3.commands._errors import command_context
from hop3.commands._response import blob, error, summary, table, text
from hop3.core.identifiers import InvalidIdentifierError, validate_service_name
from hop3.core.plugins import get_addon

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["AddonCliSpec", "generic_addon_commands"]


@dataclass(frozen=True)
class AddonCliSpec:
    """What differs between one addon type's generic CLI and another's."""

    #: The addon type as it appears in the command: `hop3 addon <type> dump`.
    type_name: str
    #: How the service is written in prose ("PostgreSQL", "Redis", "S3").
    label: str
    #: Example addon name used in help text ("mydb", "mycache", "mybucket").
    example: str
    #: Indefinite article for ``label`` — "an S3 addon", not "a S3 addon".
    article: str = "a"
    #: Dump file extension including the dot (".sql", ".rdb", ".dump").
    dump_suffix: str = ".dump"
    #: Redirect target shown in export/import help ("dump.sql", "dump").
    dump_filename: str = "dump"
    #: Tool named in the `dump` docstring, e.g. "pg_dump". Empty to omit.
    dump_tool: str = ""
    #: Tool named in the `import` docstring, e.g. "psql". Empty to omit.
    restore_tool: str = ""
    #: Where dumps are written, for the `restore` example path.
    backup_dir: str = ""
    #: What a dump of this addon holds, when it is worth saying: "keys",
    #: "manifest (credentials + bucket metadata)". Generic wording drops real
    #: information for someone deciding whether a dump is the backup they need.
    dump_contents: str = ""
    #: What the exported stream holds, when worth naming ("manifest + bucket
    #: data"). Separate from `dump_contents` so neither has to be phrased to
    #: read correctly in the other's sentence.
    export_contents: str = ""
    #: What a restore overwrites ("its database", "its bucket contents").
    restore_target: str = "the current contents of the addon"
    #: (source, target) for the clone example. Derived from ``example``
    #: otherwise, which reads badly: "clone prod-mydb staging-mydb".
    clone_example: tuple[str, str] | None = None
    #: Extra `Examples:` lines for the namespace command's help.
    namespace_examples: tuple[str, ...] = field(default_factory=tuple)

    @property
    def prefix(self) -> str:
        """The command prefix, e.g. ``hop3 addon postgres``."""
        return f"hop3 addon {self.type_name}"

    @property
    def a_label(self) -> str:
        """``label`` with its article, e.g. "an S3" / "a Redis"."""
        return f"{self.article} {self.label}"

    @property
    def clone_pair(self) -> tuple[str, str]:
        """Source and target names for the clone example."""
        return self.clone_example or (
            f"prod-{self.example}",
            f"staging-{self.example}",
        )

    @property
    def backup_path_example(self) -> str:
        directory = self.backup_dir or f"/home/hop3/backups/{self.type_name}"
        return f"{directory}/{self.example}_2026{self.dump_suffix}"


def generic_addon_commands(spec: AddonCliSpec) -> list[type[Command]]:
    """
    Build the six shared addon commands for one addon type.

    The caller registers them (``@register`` cannot decorate a class made at
    runtime the way it does a literal one) and lists them in its ``COMMANDS``
    so the plugin's ``cli_commands()`` hook contributes them.
    """
    return [
        _credentials_cmd(spec),
        _dump_cmd(spec),
        _restore_cmd(spec),
        _clone_cmd(spec),
        _export_cmd(spec),
        _import_cmd(spec),
    ]


def _make(
    spec: AddonCliSpec,
    verb: str,
    doc: str,
    call: Callable[..., list[dict]],
    *,
    destructive: bool = False,
) -> type[Command]:
    """Assemble one frozen dataclass Command class for ``verb``."""
    cls_name = f"Addon{spec.type_name.title().replace('-', '')}{verb.title()}Cmd"
    # No `__annotations__` entry for `name`/`destructive`: @dataclass turns
    # *annotated* class attributes into fields, so leaving them unannotated
    # keeps them plain class attributes — the same thing the hand-written
    # `name: ClassVar[...]` achieved, without a ClassVar in a runtime
    # annotations dict (which is not a valid annotation context).
    namespace: dict[str, object] = {
        "__doc__": doc,
        "__module__": __name__,
        "name": ("addon", spec.type_name, verb),
        "destructive": destructive,
        "call": call,
    }
    # `type()` is declared as returning bare `type`; the base is Command, so
    # the cast states what the three-argument call actually built.
    cls = cast("type[Command]", type(cls_name, (Command,), namespace))
    return dataclass(frozen=True)(cls)


def _credentials_cmd(spec: AddonCliSpec) -> type[Command]:
    def call(self: Command, *args: str) -> list[dict]:
        if not args:
            return [text(f"Usage: {spec.prefix} credentials <name>")]
        addon_name = args[0]
        with command_context(
            "reading addon credentials",
            addon_name=addon_name,
            service_type=spec.type_name,
        ):
            details = get_addon(spec.type_name, addon_name).get_connection_details()
        rows = [[key, value] for key, value in details.items()]
        return [table(headers=["Variable", "Value"], rows=rows)]

    doc = f"""Show connection credentials for {spec.a_label} addon.

    Usage: {spec.prefix} credentials <name>

    Examples:
        {spec.prefix} credentials {spec.example}
    """
    return _make(spec, "credentials", doc, call)


def _dump_cmd(spec: AddonCliSpec) -> type[Command]:
    def call(self: Command, *args: str) -> list[dict]:
        if not args:
            return [text(f"Usage: {spec.prefix} dump <name>")]
        addon_name = args[0]
        with command_context(
            "dumping addon", addon_name=addon_name, service_type=spec.type_name
        ):
            path = get_addon(spec.type_name, addon_name).backup()
        return [
            text(f"Dumped {spec.label} addon '{addon_name}' to {path}."),
            summary(f"dumped addon '{addon_name}' ({spec.type_name}) to {path}."),
        ]

    via = f" ({spec.dump_tool})" if spec.dump_tool else ""
    what = f"'s {spec.dump_contents}" if spec.dump_contents else ""
    doc = f"""Dump {spec.a_label} addon{what} to a backup file{via}.

    Usage: {spec.prefix} dump <name>

    Examples:
        {spec.prefix} dump {spec.example}
    """
    return _make(spec, "dump", doc, call)


def _restore_cmd(spec: AddonCliSpec) -> type[Command]:
    def call(self: Command, *args: str) -> list[dict]:
        if len(args) < 2:
            return [text(f"Usage: {spec.prefix} restore <name> <path>")]
        addon_name, backup_path = args[0], args[1]
        with command_context(
            "restoring addon", addon_name=addon_name, service_type=spec.type_name
        ):
            get_addon(spec.type_name, addon_name).restore(Path(backup_path))
        return [
            text(f"Restored {spec.label} addon '{addon_name}' from {backup_path}."),
            summary(
                f"restored addon '{addon_name}' ({spec.type_name}) from {backup_path}."
            ),
        ]

    doc = f"""Restore {spec.a_label} addon from a dump file.

    Usage: {spec.prefix} restore <name> <path>

    WARNING: overwrites {spec.restore_target}.

    Examples:
        {spec.prefix} restore {spec.example} {spec.backup_path_example}
    """
    return _make(spec, "restore", doc, call, destructive=True)


def _clone_cmd(spec: AddonCliSpec) -> type[Command]:
    def call(self: Command, *args: str) -> list[dict]:
        if len(args) < 2:
            return [text(f"Usage: {spec.prefix} clone <source> <new-name>")]
        source, target = args[0], args[1]
        try:
            validate_service_name(target)
        except InvalidIdentifierError as exc:
            return [error(str(exc))]
        with command_context(
            "cloning addon", addon_name=source, service_type=spec.type_name
        ):
            dst = get_addon(spec.type_name, target)
            if hasattr(dst, "exists") and dst.exists():
                return [error(f"Addon '{target}' already exists.")]
            dst.create()
            dst.restore(get_addon(spec.type_name, source).backup())
        return [
            text(f"Cloned {spec.type_name} addon '{source}' into '{target}'."),
            summary(f"cloned addon '{source}' -> '{target}' ({spec.type_name})."),
        ]

    src_name, dst_name = spec.clone_pair
    doc = f"""Clone {spec.a_label} addon into a new one (copies all data).

    Usage: {spec.prefix} clone <source> <new-name>

    Creates <new-name>, then loads a dump of <source> into it. Refuses if
    <new-name> already exists.

    Examples:
        {spec.prefix} clone {src_name} {dst_name}
    """
    return _make(spec, "clone", doc, call)


def _export_cmd(spec: AddonCliSpec) -> type[Command]:
    def call(self: Command, *args: str) -> list[dict]:
        if not args:
            return [text(f"Usage: {spec.prefix} export <name> > {spec.dump_filename}")]
        addon_name = args[0]
        with command_context(
            "exporting addon", addon_name=addon_name, service_type=spec.type_name
        ):
            path = Path(get_addon(spec.type_name, addon_name).backup())
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return [
            blob(encoded, filename=path.name),
            summary(f"exported addon '{addon_name}' ({spec.type_name})."),
        ]

    if spec.dump_tool:
        produced = f"a {spec.dump_tool} of the addon"
    elif spec.export_contents:
        produced = f"the addon's dump ({spec.export_contents})"
    else:
        produced = "the addon's dump"
    doc = f"""Stream {spec.a_label} addon dump to stdout.

    Usage: {spec.prefix} export <name> > {spec.dump_filename}

    Writes {produced} to the client's stdout — redirect it to a
    file or pipe it elsewhere.

    Examples:
        {spec.prefix} export {spec.example} > {spec.example}{spec.dump_suffix}
    """
    return _make(spec, "export", doc, call)


def _import_cmd(spec: AddonCliSpec) -> type[Command]:
    def call(
        self: Command,
        *args: str,
        import_data: str | None = None,
        **kwargs: object,
    ) -> list[dict]:
        if not args:
            return [text(f"Usage: {spec.prefix} import <name> < {spec.dump_filename}")]
        addon_name = args[0]
        if not import_data:
            return [
                error(
                    "No dump provided. Pipe one on stdin: "
                    f"{spec.prefix} import <name> < {spec.dump_filename}"
                )
            ]
        with command_context(
            "importing addon", addon_name=addon_name, service_type=spec.type_name
        ):
            content = base64.b64decode(import_data)
            with tempfile.NamedTemporaryFile(
                suffix=spec.dump_suffix, delete=False
            ) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
            try:
                get_addon(spec.type_name, addon_name).restore(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
        return [
            text(f"Imported dump into {spec.label} addon '{addon_name}'."),
            summary(f"imported dump into addon '{addon_name}' ({spec.type_name})."),
        ]

    via = f" via {spec.restore_tool}" if spec.restore_tool else ""
    doc = f"""Import a dump into {spec.a_label} addon from stdin.

    Usage: {spec.prefix} import <name> --confirm=<name> < {spec.dump_filename}

    Loads the piped dump into the addon{via}.
    Overwrites existing data; since stdin carries the dump (so it can't
    prompt), pass --confirm=<name> or --yes.

    Examples:
        {spec.prefix} import {spec.example} --confirm={spec.example} < {spec.example}{spec.dump_suffix}
    """
    return _make(spec, "import", doc, call, destructive=True)
