# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`addon s3 <verb>` commands — S3-specific addon management.

Type-agnostic addon verbs (list/create/attach/detach/destroy/show/status) live
in `hop3.commands.services`. These S3-specific level-3 commands are contributed
to the RPC dispatch table via the plugin's `cli_commands()` hook.
"""

from __future__ import annotations

from typing import ClassVar

from hop3.commands._base import Command, NamespaceCommand
from hop3.lib.decorators import register
from hop3.plugins.addons.generic_cli import (
    AddonCliSpec,
    generic_addon_commands,
)

_TYPE = "s3"

_GENERIC = AddonCliSpec(
    type_name=_TYPE,
    label="S3",
    article="an",
    example="mybucket",
    dump_suffix=".dump",
    dump_filename="dump",
    dump_contents="manifest (credentials + bucket metadata)",
    export_contents="manifest + bucket data",
    restore_target="the addon's current bucket contents / manifest",
    clone_example=("prod-bucket", "staging-bucket"),
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


# Contributed to the RPC dispatch table via S3Plugin.cli_commands().
@register
class AddonS3Cmd(NamespaceCommand):
    """
    S3 addon operations: credentials, dump/restore, and clone.

    Work with one S3 (object storage) instance: show its credentials, dump or
    restore its manifest, or clone it. Create an instance with
    'hop3 addon create s3 <name>'.

    Examples:
        hop3 addon s3 credentials myfiles               # Access key + bucket
        hop3 addon s3 dump myfiles                        # Dump the manifest
        hop3 addon s3 clone myfiles myfiles-copy          # Copy its data
    """

    name: ClassVar[tuple[str, ...]] = ("addon", _TYPE)


COMMANDS: list[type[Command]] = [
    *_GENERIC_COMMANDS,
    AddonS3Cmd,
]
