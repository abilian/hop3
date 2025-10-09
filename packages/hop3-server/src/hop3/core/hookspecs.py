# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from .hooks import hookspec


@hookspec
def cli_commands() -> None:
    """Get CLI commands."""


@hookspec
def get_build_strategies() -> list:
    """Get build strategies provided by this plugin.

    Returns:
        List of BuildStrategy classes
    """


@hookspec
def get_deployment_strategies() -> list:
    """Get deployment strategies provided by this plugin.

    Returns:
        List of DeploymentStrategy classes
    """


@hookspec
def get_service_strategies() -> list:
    """Get service strategies provided by this plugin.

    Returns:
        List of ServiceStrategy classes
    """
