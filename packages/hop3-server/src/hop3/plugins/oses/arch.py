# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""OS setup strategy for Arch Linux and derivatives.

This plugin supports:
- Arch Linux
- Manjaro
- EndeavourOS
- Any other Arch-based distribution using pacman

The plugin auto-detects the distribution and version from /etc/os-release.
"""

from __future__ import annotations

import subprocess

from hop3.core.hooks import hop3_hook_impl

from .base import BaseOSStrategy

# Package list for Arch Linux
# pacman package names
PACKAGES = [
    "bc",
    "git",
    "sudo",
    "cronie",
    # Development tools
    "base-devel",  # Includes gcc, make, etc.
    "pcre",
    "zlib",
    # Python (venv is included with python on Arch)
    "python",
    "python-pip",
    "python-click",
    "python-setuptools",
    # Nginx
    "nginx",
    "acl",
    # uwsgi (Runtime)
    "uwsgi",
    "uwsgi-plugin-python",
    # Let's Encrypt
    "certbot",
    "certbot-nginx",
    # For builders
    # - Ruby
    "ruby",
    "rubygems",
    # - Nodejs
    "nodejs",
    "npm",
    # - Go
    "go",
    # - Clojure
    "clojure",
    "leiningen",
    # - Node tools
    "yarn",
    # Addons
    "postgresql-libs",
    "postgresql",
    # Extra libs
    "cairo",
    "pango",
]


class ArchStrategy(BaseOSStrategy):
    """OS setup strategy for Arch Linux and derivatives.

    This strategy handles Arch Linux, Manjaro, EndeavourOS, and any other
    Arch-based distribution that uses pacman for package management.

    The display name is dynamically determined from /etc/os-release.
    """

    name = "arch"
    packages = PACKAGES

    @property
    def display_name(self) -> str:
        """Get display name from /etc/os-release."""
        os_info = self.read_os_release()
        pretty_name = os_info.get("PRETTY_NAME")
        if pretty_name:
            return pretty_name

        distro_id = os_info.get("ID", "Arch Linux")
        return distro_id.capitalize()

    def detect(self) -> bool:
        """Check if this is an Arch-based distribution.

        Returns True for:
        - Arch Linux
        - Manjaro
        - EndeavourOS
        - Any other distribution with ID_LIKE=arch
        """
        os_info = self.read_os_release()
        distro_id = os_info.get("ID", "")
        id_like = os_info.get("ID_LIKE", "")

        # Direct match for Arch-based distributions
        if distro_id in {"arch", "manjaro", "endeavouros"}:
            return True

        # Match distributions based on Arch
        return "arch" in id_like

    def ensure_packages(self, packages: list[str], *, update: bool = True) -> None:
        """Install packages using pacman.

        Args:
            packages: List of package names to install
            update: Whether to update package database first
        """
        if update:
            subprocess.run(
                ["pacman", "-Sy"],
                check=True,
                capture_output=True,
                text=True,
            )

        packages_str = " ".join(packages)
        cmd = f"pacman -S --noconfirm {packages_str}"
        subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)

    def setup_server(self) -> None:
        """Install dependencies and configure system for hop3.

        This setup works for Arch Linux and derivatives.
        """
        # Create hop3 user
        self.ensure_user(
            user=self.HOP3_USER,
            home=self.HOME_DIR,
            shell="/bin/bash",
            group="http",  # Arch uses 'http' group for nginx
        )

        # Install packages
        self.ensure_packages(self.packages, update=True)

        # Enable and start services
        subprocess.run(["systemctl", "enable", "nginx"], check=True)
        subprocess.run(["systemctl", "enable", "cronie"], check=True)


class ArchPlugin:
    """Plugin that provides Arch Linux OS setup strategy.

    This plugin handles Arch Linux and all derivatives including:
    - Arch Linux
    - Manjaro
    - EndeavourOS
    """

    name = "arch"

    @hop3_hook_impl
    def get_os_implementations(self) -> list:
        return [ArchStrategy]


# Plugin instance for auto-discovery
plugin = ArchPlugin()
