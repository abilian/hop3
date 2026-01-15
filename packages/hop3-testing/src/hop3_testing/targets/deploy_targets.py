# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deployment targets that wrap hop3-deploy.

This module re-exports deployment targets from their individual modules
for backward compatibility.

Classes:
    DockerDeployTarget: Uses hop3-deploy --docker for system testing
    RemoteDeployTarget: Uses hop3-deploy --host X for remote system testing
    ReadyTarget: Uses pre-built image for app testing (no deployment)
"""

from __future__ import annotations

# Re-export classes for backward compatibility
from .docker_deploy import DockerDeployTarget
from .ready import ReadyTarget
from .remote_deploy import RemoteDeployTarget

__all__ = [
    "DockerDeployTarget",
    "ReadyTarget",
    "RemoteDeployTarget",
]
