# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands to manage apps lifecycle."""

from __future__ import annotations

from argparse import ArgumentParser

from hop3.util import echo

from .base import command


@command
class PluginsCmd:
    """List installed plugins, e.g.: hop-agent plugins."""

    def run(self, _parser: ArgumentParser):
        echo("Plugins command")
