# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Backward compatibility shim - import from hop3_cli.commands instead."""

from __future__ import annotations

from .commands.flags import CliFlags, parse_flags

__all__ = ["CliFlags", "parse_flags"]
