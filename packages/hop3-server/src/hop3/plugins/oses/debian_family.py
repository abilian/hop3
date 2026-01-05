# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Generic OS setup strategy for all Debian-based distributions.

This plugin supports:
- Debian (all versions: 11, 12, 13, etc.)
- Ubuntu (all LTS versions: 20.04, 22.04, 24.04, etc.)
- Any other Debian-based distribution using APT

The plugin auto-detects the distribution and version from /etc/os-release.
"""

from __future__ import annotations

from io import StringIO

from hop3.core.hooks import hop3_hook_impl

from .debian_base import DebianBase

# Package list for all Debian-based distributions
# These package names are consistent across Debian/Ubuntu versions
PACKAGES = [
    "bc",
    "git",
    "sudo",
    "cron",
    "build-essential",
    "libpcre3-dev",
    "zlib1g-dev",
    # Python
    "python3",
    "python3-pip",
    "python3-click",
    "python3-dev",
    "python3-venv",  # Required for python3 -m venv (built-in module)
    "python3-setuptools",
    # Nginx
    "nginx",
    "acl",
    # uwsgi (Runtime)
    "uwsgi-core",
    "uwsgi-plugin-python3",
    # Let's Encrypt
    "certbot",
    # For builders
    # - Ruby
    "ruby",
    "ruby-dev",
    "ruby-bundler",
    # - Nodejs
    "npm",
    # - Go
    "golang",
    # - Clojure
    "clojure",
    "leiningen",
    # - Node tools
    "nodeenv",
    "yarnpkg",
    # Addons
    "libpq-dev",
    "postgresql",
    # Extra libs for various apps
    "libcairo2",
    "libpango-1.0-0",
    "libpangoft2-1.0-0",
]

APT_CONF = """
Acquire::http {No-Cache=True;};
APT::Install-Recommends "0";
APT::Install-Suggests "0";
Acquire::GzipIndexes "true";
Acquire::CompressionTypes::Order:: "gz";
Dir::Cache { srcpkgcache ""; pkgcache ""; }
"""


class DebianFamilyStrategy(DebianBase):
    """Generic OS setup strategy for all Debian-based distributions.

    This strategy handles Debian, Ubuntu, and any other Debian-based
    distribution that uses APT for package management.

    The display name is dynamically determined from /etc/os-release.
    """

    name = "debian-family"
    packages = PACKAGES

    @property
    def display_name(self) -> str:
        """Get display name from /etc/os-release."""
        os_info = self.read_os_release()
        # Use PRETTY_NAME if available (e.g., "Debian GNU/Linux 12 (bookworm)")
        # Otherwise construct from ID and VERSION_ID
        pretty_name = os_info.get("PRETTY_NAME")
        if pretty_name:
            return pretty_name

        distro_id = os_info.get("ID", "Debian/Ubuntu")
        version = os_info.get("VERSION_ID", "")
        return f"{distro_id.capitalize()} {version}".strip()

    def detect(self) -> bool:
        """Check if this is a Debian-based distribution.

        Returns True for:
        - Debian (all versions)
        - Ubuntu (all versions)
        - Any other distribution with ID_LIKE=debian
        """
        os_info = self.read_os_release()
        distro_id = os_info.get("ID", "")
        id_like = os_info.get("ID_LIKE", "")

        # Direct match for Debian or Ubuntu
        if distro_id in {"debian", "ubuntu"}:
            return True

        # Match distributions based on Debian (Linux Mint, Pop!_OS, etc.)
        return "debian" in id_like or "ubuntu" in id_like

    def setup_server(self) -> None:
        """Install dependencies and configure system for hop3.

        This setup is generic and works for all Debian-based distributions.
        """
        # Configure APT
        self.put_file(
            name="Configure APT optimizations",
            src=StringIO(APT_CONF),
            dest="/etc/apt/apt.conf.d/00-hop3",
        )

        # Create hop3 user
        self.ensure_user(
            user=self.HOP3_USER,
            home=self.HOME_DIR,
            shell="/bin/bash",
            group="www-data",  # Standard group for all Debian-based distros
        )

        # Install packages
        self.ensure_packages(self.packages, update=True)

        # Create symlinks for node/yarn
        # These paths are consistent across Debian/Ubuntu versions
        self.ensure_link(
            name="Create /usr/local/bin/node symlink",
            path="/usr/local/bin/node",
            target="/usr/bin/nodejs",
        )
        self.ensure_link(
            name="Create /usr/local/bin/yarn symlink",
            path="/usr/local/bin/yarn",
            target="/usr/bin/yarnpkg",
        )


class DebianFamilyPlugin:
    """Plugin that provides Debian family OS setup strategy.

    This single plugin handles all Debian-based distributions including:
    - Debian (all versions)
    - Ubuntu (all versions)
    - Linux Mint, Pop!_OS, and other Debian derivatives
    """

    name = "debian-family"

    @hop3_hook_impl
    def get_os_implementations(self) -> list:
        return [DebianFamilyStrategy]


# Plugin instance for auto-discovery
plugin = DebianFamilyPlugin()
