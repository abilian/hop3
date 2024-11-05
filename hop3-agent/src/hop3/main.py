#!/usr/bin/env python3

# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Hop3 Micro-PaaS Agent."""

from __future__ import annotations

import os
import sys
import traceback

from click import CommandCollection

from hop3.core.plugins import get_plugin_manager
from hop3.system.constants import HOP3_BIN, HOP3_TESTING
from hop3.util import Abort, prepend_to_path
from hop3.util.console import console

from .commands import hop3

TESTING = "PYTEST_VERSION" in os.environ


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

    if HOP3_TESTING:
        console.reset()

    cli = CommandCollection(sources=get_cli_commands())
    try:
        cli(args=args)
    except SystemExit as e:
        assert isinstance(e.code, int)
        if e.code == 0:
            return
        if TESTING:
            msg = "SystemExit"
            raise Abort(msg, status=e.code)
        sys.exit(e.code)
    except Abort as e:
        print(e)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
