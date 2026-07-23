# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3 use` — pin / show / clear the app for the current directory.

Per ADR 042 the app resolves from the CWD only. `hop3 use <app>` writes a
`.hop3-app` file in the current directory (app-resolution source #4 in
`hop3_cli.core.resolution`); `--clear` removes it. There is no per-context
default app anymore.

Usage:
    hop3 use <app>        Pin <app> for this directory (writes .hop3-app).
    hop3 use              Show the currently resolved app and its source.
    hop3 use --clear      Remove the .hop3-app pin for this directory.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_cli.core.resolution import resolve_app

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter

_APP_PIN = Path(".hop3-app")


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
    from .help_text import USE_HELP  # ruff:ignore[import-outside-top-level]

    print(USE_HELP)


def _set(app: str, config: Config) -> None:
    _APP_PIN.write_text(f"{app}\n")
    print(f"✓ Pinned app '{app}' for this directory (wrote {_APP_PIN}).")
    print(
        "Commands run from here will target this app automatically. "
        "Override with --app <name> or clear with `hop3 use --clear`."
    )


def _clear(config: Config) -> None:
    if _APP_PIN.exists():
        _APP_PIN.unlink()
        print(f"✓ Removed the app pin for this directory ({_APP_PIN}).")
    else:
        print("No app pin set for this directory.")


def _show(config: Config) -> None:
    resolution = resolve_app(cli_app=None)
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
