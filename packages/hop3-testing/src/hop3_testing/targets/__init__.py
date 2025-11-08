# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Target backends for Hop3 deployment testing."""

from __future__ import annotations

from .base import CommandResult, DeploymentTarget
from .docker import DockerTarget
from .remote import RemoteTarget

__all__ = [
    "CommandResult",
    "DeploymentTarget",
    "DockerTarget",
    "RemoteTarget",
]
