# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Base class for Red Hat-based distributions (DNF/YUM package management)."""

from __future__ import annotations

import subprocess

from .base import BaseOSStrategy


class RedHatBase(BaseOSStrategy):
    """Base class for Red Hat-based distributions.

    Provides DNF/YUM package management for RHEL, Rocky, Alma, Fedora, CentOS, etc.
    """

    def ensure_packages(self, packages: list[str], *, update: bool = True) -> None:
        """Install packages using DNF (or YUM as fallback).

        Args:
            packages: List of package names to install
            update: Whether to update package cache first
        """
        # Try DNF first (newer), fall back to YUM (older systems)
        pkg_manager = "dnf"
        try:
            subprocess.run(["which", "dnf"], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            pkg_manager = "yum"

        if update:
            subprocess.run(
                [pkg_manager, "check-update"],
                check=False,  # check-update returns 100 if updates available
                capture_output=True,
                text=True,
            )

        packages_str = " ".join(packages)
        cmd = f"{pkg_manager} install -y {packages_str}"
        subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
