# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Command processing for the Hop3 CLI.

This package handles command parsing and local command execution:
- local: Commands handled locally without server RPC
- help: Help flag handling and help output injection
- destructive: Confirmation prompts for destructive commands
- flags: CLI flag parsing (--json, --quiet, -y, etc.)
- arguments: Argument generation (e.g., deploy archive)
"""

from __future__ import annotations

from .arguments import generate_archive, get_extra_args, pack_repository
from .destructive import confirm_destructive_action, is_destructive_command
from .flags import CliFlags, parse_flags
from .help import (
    handle_help_flags,
    inject_local_commands_into_help,
    is_help_command,
)
from .local import (
    LOCAL_COMMANDS,
    LOCAL_COMMANDS_INFO,
    handle_local_command,
    is_local_command,
)

__all__ = [
    "LOCAL_COMMANDS",
    "LOCAL_COMMANDS_INFO",
    "CliFlags",
    "confirm_destructive_action",
    "generate_archive",
    "get_extra_args",
    "handle_help_flags",
    "handle_local_command",
    "inject_local_commands_into_help",
    "is_destructive_command",
    "is_help_command",
    "is_local_command",
    "pack_repository",
    "parse_flags",
]
