# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 deployment tool.

This module provides tools for deploying Hop3 to development/test servers.
Supports both SSH (remote servers) and Docker (local containers) backends.

Usage:
    # Via CLI
    hop3-deploy --host 192.168.1.100
    hop3-deploy --docker

    # Via Make
    make deploy                    # Deploy to HOP3_DEV_HOST
    make deploy-docker             # Deploy to local Docker container
    make deploy-local              # Deploy using local code

    # Environment variables
    HOP3_DEV_HOST=192.168.1.100 make deploy
"""

from __future__ import annotations

from .cli import main
from .config import DeployConfig
from .deploy import Deployer, create_backend, deploy

__all__ = ["DeployConfig", "Deployer", "create_backend", "deploy", "main"]
