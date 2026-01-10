# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Target backends for Hop3 deployment testing.

Target types:
- DockerTarget: Legacy target using custom Dockerfile (deprecated)
- RemoteTarget: SSH-based remote server target
- DockerDeployTarget: Uses hop3-deploy for system testing (recommended)
- ReadyTarget: Uses pre-built image for app testing (recommended)
"""

from __future__ import annotations

from .base import (
    CommandResult,
    DeploymentTarget,
    DeployResult,
    HttpResponse,
    TargetCapabilities,
    TargetInfo,
)
from .deploy_targets import DockerDeployTarget, ReadyTarget
from .docker import DockerTarget
from .remote import RemoteTarget

__all__ = [
    "CommandResult",
    "DeployResult",
    "DeploymentTarget",
    "DockerDeployTarget",
    "DockerTarget",
    "HttpResponse",
    "ReadyTarget",
    "RemoteTarget",
    "TargetCapabilities",
    "TargetInfo",
]
