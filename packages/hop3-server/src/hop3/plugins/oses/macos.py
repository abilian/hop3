# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""OS setup strategy for macOS.

This plugin supports macOS (all versions) using Homebrew for package management.
"""

from __future__ import annotations

import pathlib
import platform
import subprocess

from hop3.core.hooks import hop3_hook_impl

from .base import BaseOSStrategy

# Package list for macOS (Homebrew formula names)
PACKAGES = [
    "git",
    # Python (macOS has python3 built-in, but we want brew version)
    "python@3.11",
    # Nginx
    "nginx",
    # uwsgi
    "uwsgi",
    # Let's Encrypt
    "certbot",
    # For builders
    # - Ruby (macOS has ruby built-in, but we want brew version)
    "ruby",
    # - Nodejs
    "node",
    "yarn",
    # - Go
    "go",
    # - Clojure
    "clojure",
    "leiningen",
    # Addons
    "postgresql@15",
    # Extra libs
    "cairo",
    "pango",
]


class MacOSStrategy(BaseOSStrategy):
    """OS setup strategy for macOS.

    This strategy handles macOS using Homebrew for package management.
    Requires Homebrew to be installed (https://brew.sh).
    """

    name = "macos"
    packages = PACKAGES

    @property
    def display_name(self) -> str:
        """Get macOS version."""
        try:
            version = platform.mac_ver()[0]
            return f"macOS {version}"
        except Exception:
            return "macOS"

    def detect(self) -> bool:
        """Check if this is macOS."""
        return platform.system() == "Darwin"

    def ensure_packages(self, packages: list[str], *, update: bool = True) -> None:
        """Install packages using Homebrew.

        Args:
            packages: List of package/formula names to install
            update: Whether to update Homebrew first
        """
        # Check if Homebrew is installed
        try:
            subprocess.run(
                ["which", "brew"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            msg = "Homebrew is not installed. Please install from https://brew.sh"
            raise RuntimeError(msg)

        if update:
            subprocess.run(["brew", "update"], check=True, capture_output=True)

        for package in packages:
            # Check if already installed
            result = subprocess.run(
                ["brew", "list", package],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                continue  # Already installed

            subprocess.run(
                ["brew", "install", package],
                check=True,
                capture_output=True,
                text=True,
            )

    def ensure_user(
        self, user: str, home: str, shell: str, group: str | None = None
    ) -> None:
        """Create a system user on macOS.

        Note: macOS user management is different from Linux.
        This creates a standard user account.
        """
        # Check if user exists
        try:
            subprocess.run(
                ["id", user],
                check=True,
                capture_output=True,
                text=True,
            )
            return  # User exists
        except subprocess.CalledProcessError:
            pass

        # Create user using dscl (Directory Service command line)
        # This is macOS-specific user creation

        # Find next available UID (start from 501, which is standard for macOS user accounts)
        uid = 501
        while pathlib.Path(f"/Users/{user}").exists():
            uid += 1

        # Create user
        subprocess.run(
            ["sudo", "dscl", ".", "-create", f"/Users/{user}"],
            check=True,
        )
        subprocess.run(
            ["sudo", "dscl", ".", "-create", f"/Users/{user}", "UserShell", shell],
            check=True,
        )
        subprocess.run(
            ["sudo", "dscl", ".", "-create", f"/Users/{user}", "UniqueID", str(uid)],
            check=True,
        )
        subprocess.run(
            [
                "sudo",
                "dscl",
                ".",
                "-create",
                f"/Users/{user}",
                "PrimaryGroupID",
                "20",
            ],  # staff group
            check=True,
        )
        subprocess.run(
            [
                "sudo",
                "dscl",
                ".",
                "-create",
                f"/Users/{user}",
                "NFSHomeDirectory",
                home,
            ],
            check=True,
        )

        # Create home directory
        subprocess.run(["sudo", "mkdir", "-p", home], check=True)
        subprocess.run(["sudo", "chown", f"{user}:staff", home], check=True)

    def setup_server(self) -> None:
        """Install dependencies and configure macOS for hop3.

        Note: macOS setup differs from Linux:
        - Uses Homebrew instead of apt/yum/pacman
        - Uses launchctl for services instead of systemctl
        - Different user/group model (staff instead of www-data)
        """
        # Create hop3 user (uses 'staff' group on macOS)
        self.ensure_user(
            user=self.HOP3_USER,
            home=self.HOME_DIR,
            shell="/bin/bash",
            group="staff",
        )

        # Install packages
        self.ensure_packages(self.packages, update=True)

        # Start services using Homebrew services
        subprocess.run(["brew", "services", "start", "nginx"], check=False)
        subprocess.run(["brew", "services", "start", "postgresql@15"], check=False)


class MacOSPlugin:
    """Plugin that provides macOS OS setup strategy."""

    name = "macos"

    @hop3_hook_impl
    def get_os_implementations(self) -> list:
        return [MacOSStrategy]


# Plugin instance for auto-discovery
plugin = MacOSPlugin()
