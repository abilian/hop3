# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from io import StringIO

from hop3.oses.helpers import Debian

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
    "python3-virtualenv",
    "python3-setuptools",
    # Nginx
    "nginx",
    "acl",
    # uwsgi
    "uwsgi-core",
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
    "uwsgi-plugin-python3",
    # - Nodejs
    "npm",
    "nodeenv",
    "yarnpkg",
    # Addons
    "libpq-dev",
    "postgresql",
]

HOP3_USER = "hop3"
SSH_USER = "root"
HOME_DIR = f"/home/{HOP3_USER}"
VENV = f"{HOME_DIR}/venv"
HOP_SCRIPT = f"{VENV}/bin/hop-agent"

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
    and symlinks.

    This performs the following tasks:

    - Puts a configuration file at a specified location.
    - Ensures a specific user with defined attributes exists.
    - Installs a list of Debian packages and performs an update.
    - Creates symbolic links for node and yarn commands.
    """

    platform.put_file(
        name="Put appropriate /etc/apt/apt.conf.d/00-nua",
        src=StringIO(
            APT_CONF
        ),  # Using StringIO to create an in-memory file from the APT_CONF string
        dest="/etc/apt/apt.conf.d/00-hop3",  # Destination path for the configuration file
    )
    platform.ensure_user(
        name="Add hop3 user",
        user=HOP3_USER,  # The username to ensure exists
        home=HOME_DIR,  # Home directory for the user
        shell="/bin/bash",  # Default shell for the user
        group="www-data",  # Group to which the user should belong
    )

    platform.ensure_packages(
        name="Install Debian Packages",
        packages=PACKAGES,  # List of packages to install
        update=True,  # Indicates that an update should be performed before installation
    )
    platform.ensure_link(
        name="Create /usr/local/bin/node symlink",
        path="/usr/local/bin/node",  # Path for the symlink
        target="/usr/bin/nodejs",  # Target file the symlink points to
    )
    platform.ensure_link(
        name="Create /usr/local/bin/yarn symlink",
        path="/usr/local/bin/yarn",  # Path for the symlink
        target="/usr/bin/yarnpkg",  # Target file the symlink points to
    )
