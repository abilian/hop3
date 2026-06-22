# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Email (SMTP relay) addon plugin registration — EXPERIMENTAL."""

from __future__ import annotations

from hop3.core.hooks import hookimpl

from . import cli
from .email import EmailAddon

assert cli  # imported for side effects (command registration)


class EmailPlugin:
    """Email addon plugin for Hop3 (experimental)."""

    name = "email"

    @hookimpl
    def get_addons(self) -> list:
        """Return the email addon implementation."""
        return [EmailAddon]

    @hookimpl
    def cli_commands(self) -> list:
        """Contribute `addon email <verb>` commands to the CLI."""
        return cli.COMMANDS


# Auto-registered when this module is imported by scan_package("hop3.plugins").
plugin = EmailPlugin()
