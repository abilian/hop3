# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from .hooks import hop3_hook_spec
from .protocols import BuildStrategy, DeploymentStrategy


# --- Hook Specification Container ---
class Hop3Spec:
    @hop3_hook_spec
    def get_build_strategies(self) -> list[type[BuildStrategy]]:
        """A hook for plugins to return their BuildStrategy classes."""
        return []  # Default empty implementation

    @hop3_hook_spec
    def get_deployment_strategies(self) -> list[type[DeploymentStrategy]]:
        """A hook for plugins to return their DeploymentStrategy classes."""
        return []  # Default empty implementation

    # @hop3_hook_spec
    # def register_cli_commands(self) -> List[Type[TODO]]:
    #     """A hook for plugins to return their CLI commands."""
    #     return []  # Default empty implementation
    #
