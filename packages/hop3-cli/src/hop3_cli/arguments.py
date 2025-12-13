# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Backward compatibility shim - import from hop3_cli.commands instead."""

from __future__ import annotations

from .commands.arguments import (
    generate_archive,
    get_extra_args,
    get_files_to_add,
    get_ignored_spec,
    pack_repository,
)

__all__ = [
    "generate_archive",
    "get_extra_args",
    "get_files_to_add",
    "get_ignored_spec",
    "pack_repository",
]
