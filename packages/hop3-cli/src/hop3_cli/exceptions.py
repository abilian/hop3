# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI exceptions."""

from __future__ import annotations


class CliError(Exception):
    """Base class for CLI exceptions."""


class AuthenticationError(CliError):
    """Raised when authentication fails."""


class DeploymentError(CliError):
    """Raised when a deployment fails."""


class ConfigError(CliError):
    """Raised when the CLI configuration cannot be loaded (e.g. malformed TOML)."""


class TargetError(CliError):
    """
    Raised when no server can be chosen for this command (ADR 042).

    Carries the refusal and the command that fixes it. Raised only when a
    command needs a server, so commands that never reach one still run.
    """
