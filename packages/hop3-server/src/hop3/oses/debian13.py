# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Setup script for Debian 13 (Trixie)."""

from __future__ import annotations

from io import StringIO

from hop3.oses.helpers import Debian

# Package list for Debian 13
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
    "python3-venv",  # Required for python3 -m venv
    "python3-virtualenv",
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

HOP3_USER = "hop3"
SSH_USER = "root"
HOME_DIR = f"/home/{HOP3_USER}"
VENV = f"{HOME_DIR}/venv"
HOP_SCRIPT = f"{VENV}/bin/hop-server"

APT_CONF = """
Acquire::http {No-Cache=True;};
APT::Install-Recommends "0";
APT::Install-Suggests "0";
Acquire::GzipIndexes "true";
Acquire::CompressionTypes::Order:: "gz";
Dir::Cache { srcpkgcache ""; pkgcache ""; }
"""

platform = Debian()


def setup_server() -> None:
    """Configures the server by setting up necessary files, users, packages,
    and symlinks for Debian 13 (Trixie).

    This performs the following tasks:

    - Puts an APT configuration file at a specified location.
    - Ensures the hop3 user with defined attributes exists.
    - Installs required Debian packages and performs an update.
    - Creates symbolic links for node and yarn commands.
    """

    platform.put_file(
        name="Put appropriate /etc/apt/apt.conf.d/00-hop3",
        src=StringIO(APT_CONF),
        dest="/etc/apt/apt.conf.d/00-hop3",
    )
    platform.ensure_user(
        name="Add hop3 user",
        user=HOP3_USER,
        home=HOME_DIR,
        shell="/bin/bash",
        group="www-data",
    )

    platform.ensure_packages(
        name="Install Debian Packages",
        packages=PACKAGES,
        update=True,
    )
    platform.ensure_link(
        name="Create /usr/local/bin/node symlink",
        path="/usr/local/bin/node",
        target="/usr/bin/nodejs",
    )
    platform.ensure_link(
        name="Create /usr/local/bin/yarn symlink",
        path="/usr/local/bin/yarn",
        target="/usr/bin/yarnpkg",
    )
