# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from io import StringIO

from hop3.installer.helpers import Debian

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


def setup_server():
    platform.put_file(
        name="Put appropriate /etc/apt/apt.conf.d/00-nua",
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
