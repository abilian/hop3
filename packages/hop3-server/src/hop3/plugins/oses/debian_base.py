# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Base class for Debian-based OS strategies (Debian, Ubuntu)."""

from __future__ import annotations

import subprocess

from .base import BaseOSStrategy


class DebianBase(BaseOSStrategy):
    """Base class for Debian-based distributions.

    Provides APT package management functionality that's common
    to all Debian-based systems (Debian, Ubuntu, etc.).
    """

    def ensure_packages(self, packages: list[str], *, update: bool = True) -> None:
        """Install packages using APT.

        Args:
            packages: List of package names to install
            update: Whether to run apt-get update first
        """
        if update:
            subprocess.run(
                ["apt-get", "update"],
                check=True,
                capture_output=True,
                text=True,
            )

        # Install packages
        packages_str = " ".join(packages)
        cmd = f"apt-get install -y {packages_str}"
        subprocess.run(
            cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
        )
