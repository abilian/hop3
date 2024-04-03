"""
=== CLI commands ===
"""

from __future__ import annotations

from click import pass_context
from click import secho as echo

from .cli import hop3


@hop3.command("help")
@pass_context
def cmd_help(ctx) -> None:
    """Display help for hop3"""
    echo(ctx.parent.get_help())
