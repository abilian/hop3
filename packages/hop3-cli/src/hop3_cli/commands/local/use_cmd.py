# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 use` — set / show / clear the current context's default app.

Per ADR 036 D7/D8, `hop3 use <app>` is sugar for setting the active context's
`default_app`, which then acts as source #5 of the implicit-app chain
(see `hop3_cli.core.resolution`).

Usage:
    hop3 use <app>        Set the current context's default app.
    hop3 use              Show the currently resolved app and its source.
    hop3 use --clear      Clear the default app for the current context.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from hop3_cli.core.resolution import resolve_app

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_use(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Handle the `hop3 use` command."""
    if "--help" in args or "-h" in args:
        _show_help()
        return

    clear = "--clear" in args
    positional = [a for a in args if not a.startswith("-")]

    if clear and positional:
        print("Error: cannot combine --clear with an app name.", file=sys.stderr)
        return

    if clear:
        _clear(config)
        return

    if positional:
        _set(positional[0], config)
        return

    # No args: show current resolved app and source.
    _show(config)


def _show_help() -> None:
    from .help_text import USE_HELP  # noqa: PLC0415

    print(USE_HELP)


def _set(app: str, config: Config) -> None:
    try:
        context = config.set_default_app(app)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return
    print(f"✓ Default app for context '{context}' set to '{app}'.")
    print(
        "Commands that take --app will now use this value automatically. "
        "Override with --app <name> or clear with `hop3 use --clear`."
    )


def _clear(config: Config) -> None:
    try:
        context = config.set_default_app(None)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return
    print(f"✓ Cleared default app for context '{context}'.")


def _show(config: Config) -> None:
    resolution = resolve_app(cli_app=None, config=config)
    if resolution.resolved:
        print(f"app:     {resolution.app}")
        print(f"source:  {resolution.source}")
    else:
        print("app:     (none resolved)")
        print()
        print(
            "No app is set. Try one of:\n"
            "  hop3 use <app>                # set for the current context\n"
            "  export HOP3_APP=<app>         # set for this shell session\n"
            "  echo <app> > .hop3-app        # set for this directory\n"
            "  hop3 <cmd> --app <app>        # one-time override"
        )
