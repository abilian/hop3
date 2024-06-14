#!/usr/bin/env python3

# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Hop3 Micro-PaaS Agent."""

from __future__ import annotations

import os
import sys
import traceback

from click import CommandCollection

from hop3.core.plugins import get_plugin_manager
from hop3.system.constants import HOP3_BIN
from hop3.util import Abort
from hop3.util.path import prepend_to_path

from .commands import hop3


def fix_path() -> None:
    """Ensure system binaries are in the PATH, as wel as hop3 binaries."""
    path = os.environ["PATH"]
    path = prepend_to_path([HOP3_BIN, "/usr/local/sbin", "/usr/sbin", "/sbin"], path)
    os.environ["PATH"] = path


def get_cli_commands():
    cli_commands = [hop3]

    # Use pluggy to get all the plugins
    pm = get_plugin_manager()
    cli_commands += pm.hook.cli_commands()

    return cli_commands


def main(args=None) -> None:
    if not args:
        args = sys.argv[1:]

    fix_path()
    cli = CommandCollection(sources=get_cli_commands())
    try:
        cli(args=args)
    except Abort as e:
        print(e)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
