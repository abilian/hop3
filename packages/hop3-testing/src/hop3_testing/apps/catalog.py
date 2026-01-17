# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test application data class for deployment sessions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppSource:
    """Represents a test application for deployment.

    This is a simple data class used by DeploymentSession to track
    app metadata during deployment and testing.
    """

    name: str
    path: Path
    category: str = ""
    description: str = ""

    @property
    def has_check_script(self) -> bool:
        """Check if app has a check.py script."""
        return (self.path / "check.py").exists()

    @property
    def has_procfile(self) -> bool:
        """Check if app has a Procfile."""
        return (self.path / "Procfile").exists()
