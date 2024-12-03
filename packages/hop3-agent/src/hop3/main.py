#!/usr/bin/env python3

# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Hop3 Micro-PaaS Agent."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from hop3.cli.main import CLI
from hop3.config import config
from hop3.util import Abort
from hop3.util.console import console

TESTING = "PYTEST_VERSION" in os.environ


# def get_cli_commands():
#     cli_commands = [hop3]
#
#     # Use pluggy to get all the plugins
#     pm = get_plugin_manager()
#     cli_commands += pm.hook.cli_commands()
#
#     return cli_commands


def set_config():
    if "HOP3_HOME" in os.environ:
        home = Path(os.environ["HOP3_HOME"])
        config.set_home(home)

    if "HOP3_USER" in os.environ:
        user = os.environ["HOP3_USER"]
        config.set_user(user)

    if TESTING:
        config.set_home("/tmp/hop3")
        console.reset()


def main(args=None) -> None:
    set_config()

    if not args:
        args = sys.argv[1:]

    # FIXME: this could got to conftest.py now.

    # cli = CommandCollection(sources=get_cli_commands())
    cli = CLI()

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
