# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Generic OS setup strategy for all Red Hat-based distributions.

This plugin supports:
- RHEL (Red Hat Enterprise Linux)
- Rocky Linux
- AlmaLinux
- Fedora
- CentOS (7+)
- Any other Red Hat-based distribution using DNF/YUM

The plugin auto-detects the distribution and version from /etc/os-release.
"""

from __future__ import annotations

import subprocess
from io import StringIO

from hop3.core.hooks import hop3_hook_impl

from .redhat_base import RedHatBase

# Package list for Red Hat-based distributions
# DNF/YUM package names
PACKAGES = [
    "bc",
    "git",
    "sudo",
    "cronie",  # cron on RHEL
    # Development tools
    "gcc",
    "gcc-c++",
    "make",
    "pcre-devel",
    "zlib-devel",
    # Python (venv is included with python3 on RHEL/Fedora)
    "python3",
    "python3-pip",
    "python3-devel",
    "python3-setuptools",
    # Nginx
    "nginx",
    "acl",
    # uwsgi (Runtime)
    "uwsgi",
    "uwsgi-plugin-python3",
    # Let's Encrypt
    "certbot",
    "python3-certbot-nginx",
    # For builders
    # - Ruby
    "ruby",
    "ruby-devel",
    "rubygem-bundler",
    # - Nodejs
    "nodejs",
    "npm",
    # - Go
    "golang",
    # - Node tools
    "yarnpkg",
    # Addons
    "postgresql-devel",
    "postgresql-server",
    # Extra libs
    "cairo",
    "pango",
]

DNF_CONF = """
[main]
keepcache=0
install_weak_deps=False
"""


class RedHatFamilyStrategy(RedHatBase):
    """Generic OS setup strategy for all Red Hat-based distributions.

    This strategy handles RHEL, Rocky, Alma, Fedora, CentOS, and any other
    Red Hat-based distribution that uses DNF/YUM for package management.

    The display name is dynamically determined from /etc/os-release.
    """

    name = "redhat-family"
    packages = PACKAGES

    @property
    def display_name(self) -> str:
        """Get display name from /etc/os-release."""
        os_info = self.read_os_release()
        # Use PRETTY_NAME if available
        pretty_name = os_info.get("PRETTY_NAME")
        if pretty_name:
            return pretty_name

        distro_id = os_info.get("ID", "RHEL/Rocky/Alma")
        version = os_info.get("VERSION_ID", "")
        return f"{distro_id.upper()} {version}".strip()

    def detect(self) -> bool:
        """Check if this is a Red Hat-based distribution.

        Returns True for:
        - RHEL (all versions)
        - Rocky Linux (all versions)
        - AlmaLinux (all versions)
        - Fedora (all versions)
        - CentOS (all versions)
        - Any other distribution with ID_LIKE=rhel or ID_LIKE=fedora
        """
        os_info = self.read_os_release()
        distro_id = os_info.get("ID", "")
        id_like = os_info.get("ID_LIKE", "")

        # Direct match for Red Hat family distributions
        if distro_id in {"rhel", "rocky", "almalinux", "alma", "fedora", "centos"}:
            return True

        # Match distributions based on RHEL or Fedora
        return "rhel" in id_like or "fedora" in id_like

    def setup_server(self) -> None:
        """Install dependencies and configure system for hop3.

        This setup is generic and works for all Red Hat-based distributions.
        """
        # Configure DNF
        self.put_file(
            name="Configure DNF optimizations",
            src=StringIO(DNF_CONF),
            dest="/etc/dnf/dnf.conf",
        )

        # Create hop3 user
        self.ensure_user(
            user=self.HOP3_USER,
            home=self.HOME_DIR,
            shell="/bin/bash",
            group="nginx",  # RHEL uses 'nginx' group instead of 'www-data'
        )

        # Install packages
        self.ensure_packages(self.packages, update=True)

        # Enable and start services

        subprocess.run(["systemctl", "enable", "nginx"], check=True)
        subprocess.run(["systemctl", "enable", "crond"], check=True)


class RedHatFamilyPlugin:
    """Plugin that provides Red Hat family OS setup strategy.

    This single plugin handles all Red Hat-based distributions including:
    - RHEL (all versions)
    - Rocky Linux (all versions)
    - AlmaLinux (all versions)
    - Fedora (all versions)
    - CentOS (all versions)
    """

    name = "redhat-family"

    @hop3_hook_impl
    def get_os_implementations(self) -> list:
        return [RedHatFamilyStrategy]


# Plugin instance for auto-discovery
plugin = RedHatFamilyPlugin()
