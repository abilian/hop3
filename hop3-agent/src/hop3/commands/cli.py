# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands group."""

from __future__ import annotations

from click import group, pass_context
from devtools import debug

from hop3.util.console import echo

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@group(context_settings=CONTEXT_SETTINGS)
def hop3() -> None:
    """Small, open source, extensible PaaS."""


@hop3.result_callback()
def cleanup(ctx) -> None:
    """Callback from command execution -- add debugging to taste."""
    debug(ctx)


@hop3.command("help")
@pass_context
def cmd_help(ctx) -> None:
    """Display help for hop3."""
    help_msg = ctx.parent.get_help()
    lines = help_msg.split("\n")
    lines = [line for line in lines if "INTERNAL:" not in line]
    help_msg = "\n".join(lines)
    echo(help_msg)
