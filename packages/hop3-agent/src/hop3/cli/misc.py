# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands to manage apps lifecycle."""

from __future__ import annotations

from hop3.util import echo

from ._base import Cmd, command


@command
class HelpCmd(Cmd):
    """List apps, e.g.: hop-agent apps."""

    def run(self):
        echo("Help command")
