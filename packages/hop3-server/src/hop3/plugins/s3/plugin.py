# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""S3 plugin registration and health check for Hop3."""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

from hop3.core.hooks import hookimpl
from hop3.core.protocols import HealthCheckResult

from . import cli
from .backend import get_default_backend
from .s3 import S3Addon

assert cli  # imported for side effects (command registration)

if TYPE_CHECKING:
    from .backend import S3Backend


class S3HealthCheck:
    """Health check for S3 backend connectivity.

    S3 is optional, so a missing backend reports as "not configured"
    rather than a hard failure.
    """

    name = "s3"

    def is_configured(self) -> bool:
        """S3 is considered configured if the mc CLI is available.

        (MinIO backend only — Garage will check a different binary.)
        """
        return shutil.which("mc") is not None

    def check(self) -> HealthCheckResult:
        """Test S3 backend connectivity."""
        if not self.is_configured():
            return HealthCheckResult(
                name="S3",
                passed=True,
                message="S3 backend not installed (skipped)",
            )

        try:
            backend: S3Backend = get_default_backend()
            # Try a no-op list to verify the backend is reachable
            backend.list_buckets()
            return HealthCheckResult(
                name="S3",
                passed=True,
                message=f"Connection successful ({backend.name} at {backend.endpoint})",
                details={"backend": backend.name, "endpoint": backend.endpoint},
            )
        except (subprocess.CalledProcessError, NotImplementedError, Exception) as e:
            # S3 is optional — a missing/unreachable backend is not fatal
            return HealthCheckResult(
                name="S3",
                passed=True,
                message=f"Not accessible: {e}",
            )


class S3Plugin:
    """S3 addon plugin for Hop3."""

    name = "s3"

    @hookimpl
    def get_addons(self) -> list:
        """Return S3 addon implementation."""
        return [S3Addon]

    @hookimpl
    def get_health_checks(self) -> list:
        """Return S3 health check."""
        return [S3HealthCheck()]


# Auto-register plugin instance when module is imported
plugin = S3Plugin()
