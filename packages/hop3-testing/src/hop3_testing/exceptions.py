# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Exceptions for the hop3-testing package."""

from __future__ import annotations


class TestingError(Exception):
    """Base class for testing exceptions."""


class ServiceStartError(TestingError):
    """Raised when a service fails to start."""


class DeploymentError(TestingError):
    """Raised when a deployment fails."""


class CleanupError(TestingError):
    """Raised when cleanup fails."""


class ConfigurationError(TestingError):
    """Raised when configuration fails."""
