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
