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
        # SECURITY: ``packages`` is fanned out into ``apt-get install -y *names``.
        # Today every caller passes a static module-level list, but reject
        # anything with shell metacharacters anyway — see
        # BaseOSStrategy._validate_package_names.
        self._validate_package_names(packages)

        if update:
            subprocess.run(
                ["apt-get", "update"],
                check=True,
                capture_output=True,
                text=True,
            )

        # Install packages
        cmd = ["apt-get", "install", "-y", *packages]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
