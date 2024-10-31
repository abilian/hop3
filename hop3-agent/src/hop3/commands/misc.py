# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""=== CLI commands ===."""

from __future__ import annotations

from click import pass_context

from hop3.util.console import echo

from .cli import hop3


@hop3.command("help")
@pass_context
def cmd_help(ctx) -> None:
    """Display help for hop3."""
    help_msg = ctx.parent.get_help()
    lines = help_msg.split("\n")
    lines = [line for line in lines if "INTERNAL:" not in line]
    help_msg = "\n".join(lines)
    echo(help_msg)
