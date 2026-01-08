# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Test backends for installer testing."""

from __future__ import annotations

from .base import Backend
from .docker import DockerBackend
from .ssh import SSHBackend
from .vagrant import VagrantBackend

__all__ = [
    "Backend",
    "DockerBackend",
    "SSHBackend",
    "VagrantBackend",
]
