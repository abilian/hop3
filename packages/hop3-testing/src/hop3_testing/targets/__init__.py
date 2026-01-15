# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Target backends for Hop3 deployment testing.

Target types:
- DockerTarget: Legacy target using custom Dockerfile (deprecated)
- RemoteTarget: SSH-based remote server target
- DockerDeployTarget: Uses hop3-deploy for system testing (recommended)
- RemoteDeployTarget: Uses hop3-deploy for remote server testing (recommended)
- ReadyTarget: Uses pre-built image for app testing (recommended)

Helpers (composition over inheritance):
- HealthChecker: Health check logic for targets
- DiagnosticsHelper: Diagnostics save/dump operations
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
from .constants import HEALTH_CHECK_COMMAND, HEALTHY_STATUS_CODES
from .deploy_base import DeployTargetBase
from .deploy_targets import DockerDeployTarget, ReadyTarget, RemoteDeployTarget
from .docker import DockerTarget
from .helpers import DiagnosticsHelper, HealthChecker, find_project_root
from .remote import RemoteTarget

__all__ = [
    "HEALTHY_STATUS_CODES",
    "HEALTH_CHECK_COMMAND",
    "CommandResult",
    "DeployResult",
    "DeployTargetBase",
    "DeploymentTarget",
    "DiagnosticsHelper",
    "DockerDeployTarget",
    "DockerTarget",
    "HealthChecker",
    "HttpResponse",
    "ReadyTarget",
    "RemoteDeployTarget",
    "RemoteTarget",
    "TargetCapabilities",
    "TargetInfo",
    "find_project_root",
]
