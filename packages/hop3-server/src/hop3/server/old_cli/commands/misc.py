# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""CLI commands to manage apps lifecycle."""

from __future__ import annotations

from argparse import ArgumentParser

from hop3.lib import echo
from hop3.server.commands.registry import command


@command
class PluginsCmd:
    """List installed plugins."""

    def run(self, _parser: ArgumentParser):
        echo("Plugins command")
