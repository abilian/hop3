# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""OS setup strategy for BSD systems (FreeBSD, OpenBSD, etc.).

This plugin supports:
- FreeBSD (all versions)
- OpenBSD (all versions)
"""

from __future__ import annotations

import pathlib
import platform
import subprocess

from hop3.core.hooks import hop3_hook_impl

from .base import BaseOSStrategy

# Package list for FreeBSD (pkg names)
# Note: venv is included with python39 on FreeBSD
FREEBSD_PACKAGES = [
    "git",
    "sudo",
    # Python (venv is included with python39)
    "python39",
    "py39-pip",
    "py39-setuptools",
    # Nginx
    "nginx",
    # uwsgi
    "uwsgi",
    "uwsgi-python39",
    # Let's Encrypt
    "py39-certbot",
    "py39-certbot-nginx",
    # For builders
    # - Ruby
    "ruby",
    "ruby-gems",
    # - Nodejs
    "node",
    "npm",
    "yarn",
    # - Go
    "go",
    # Addons
    "postgresql15-client",
    "postgresql15-server",
    # Extra libs
    "cairo",
    "pango",
]

# Package list for OpenBSD (pkg_add names)
# Note: venv is included with python3 on OpenBSD
OPENBSD_PACKAGES = [
    "git",
    # Python (venv is included with python3)
    "python3",
    "py3-pip",
    # Nginx
    "nginx",
    # For builders
    # - Ruby
    "ruby",
    # - Nodejs
    "node",
    # - Go
    "go",
    # Addons
    "postgresql-server",
]


class BSDStrategy(BaseOSStrategy):
    """OS setup strategy for BSD systems.

    This strategy handles FreeBSD and OpenBSD with their respective
    package managers (pkg for FreeBSD, pkg_add for OpenBSD).
    """

    name = "bsd"

    @property
    def display_name(self) -> str:
        """Get BSD variant and version."""
        system = platform.system()
        release = platform.release()
        return f"{system} {release}"

    @property
    def packages(self) -> list[str]:
        """Get appropriate package list based on BSD variant."""
        system = platform.system()
        if system == "FreeBSD":
            return FREEBSD_PACKAGES
        if system == "OpenBSD":
            return OPENBSD_PACKAGES
        return []

    def detect(self) -> bool:
        """Check if this is a BSD system."""
        system = platform.system()
        return system in {"FreeBSD", "OpenBSD", "NetBSD"}

    def ensure_packages(self, packages: list[str], *, update: bool = True) -> None:
        """Install packages using appropriate BSD package manager.

        Args:
            packages: List of package names to install
            update: Whether to update package database first
        """
        system = platform.system()

        if system == "FreeBSD":
            # FreeBSD uses pkg
            if update:
                subprocess.run(
                    ["pkg", "update"],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            for package in packages:
                subprocess.run(
                    ["pkg", "install", "-y", package],
                    check=True,
                    capture_output=True,
                    text=True,
                )

        elif system == "OpenBSD":
            # OpenBSD uses pkg_add
            if update:
                # pkg_add doesn't have an update command
                pass

            for package in packages:
                subprocess.run(
                    ["pkg_add", "-I", package],
                    check=True,
                    capture_output=True,
                    text=True,
                )

    def setup_server(self) -> None:
        """Install dependencies and configure BSD system for hop3."""
        system = platform.system()

        # Create hop3 user
        # BSD uses 'www' group for web server
        self.ensure_user(
            user=self.HOP3_USER,
            home=self.HOME_DIR,
            shell="/bin/sh",
            group="www",
        )

        # Install packages
        self.ensure_packages(self.packages, update=True)

        # Enable services based on BSD variant
        if system == "FreeBSD":
            # FreeBSD uses rc.conf
            with pathlib.Path("/etc/rc.conf").open("a") as f:
                f.write("\n# hop3 services\n")
                f.write('nginx_enable="YES"\n')
                f.write('postgresql_enable="YES"\n')

            # Start services
            subprocess.run(["service", "nginx", "start"], check=False)
            subprocess.run(["service", "postgresql", "start"], check=False)

        elif system == "OpenBSD":
            # OpenBSD uses rcctl
            subprocess.run(["rcctl", "enable", "nginx"], check=False)
            subprocess.run(["rcctl", "start", "nginx"], check=False)


class BSDPlugin:
    """Plugin that provides BSD OS setup strategy.

    This plugin handles:
    - FreeBSD (all versions)
    - OpenBSD (all versions)
    """

    name = "bsd"

    @hop3_hook_impl
    def get_os_implementations(self) -> list:
        return [BSDStrategy]


# Plugin instance for auto-discovery
plugin = BSDPlugin()
