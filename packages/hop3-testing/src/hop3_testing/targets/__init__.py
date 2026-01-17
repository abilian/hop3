# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Target backends for Hop3 deployment testing.

Target types:
- DockerTarget: All Docker-based scenarios (pre-built image, Dockerfile, or deploy)
- RemoteTarget: All SSH-based scenarios (connect-only or deploy)

Configuration classes:
- DockerConfig: Configuration for Docker targets
- RemoteConfig: Configuration for remote targets
- DeploymentConfig: Optional configuration for Hop3 deployment

Helpers (composition over inheritance):
- HealthChecker: Health check logic for targets
- DiagnosticsHelper: Diagnostics save/dump operations
- DockerContainerHelper: Docker container operations
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
from .config import DeploymentConfig, DockerConfig, RemoteConfig
from .constants import HEALTH_CHECK_COMMAND, HEALTHY_STATUS_CODES
from .docker import DockerTarget
from .helpers import (
    DiagnosticsHelper,
    DockerContainerHelper,
    HealthChecker,
    find_project_root,
)
from .remote import RemoteTarget

__all__ = [
    "HEALTHY_STATUS_CODES",
    "HEALTH_CHECK_COMMAND",
    "CommandResult",
    "DeployResult",
    "DeploymentConfig",
    "DeploymentTarget",
    "DiagnosticsHelper",
    "DockerConfig",
    "DockerContainerHelper",
    "DockerTarget",
    "HealthChecker",
    "HttpResponse",
    "RemoteConfig",
    "RemoteTarget",
    "TargetCapabilities",
    "TargetInfo",
    "find_project_root",
]
