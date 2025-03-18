#!/usr/bin/env python3

# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Hop3 Micro-PaaS Agent."""

from __future__ import annotations

import os
import sys
import traceback

from hop3.cli.main import CLI
from hop3.util import Abort
from hop3.util.console import console

TESTING = "PYTEST_VERSION" in os.environ


def main(args=None) -> None:
    if TESTING:
        console.reset()

    if not args:
        args = sys.argv[1:]

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
