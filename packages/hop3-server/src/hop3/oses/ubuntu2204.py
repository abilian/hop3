# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Install Hop3 on Ubuntu 22.04 LTS."""

from __future__ import annotations

import os

from hop3.oses.common import HOME_DIR, HOP3_USER

# from pyinfra import host
# from pyinfra.facts.files import File
# from pyinfra.operations import apt, files, pip, server, systemd


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
    # uwsgi (Runtime)
    "uwsgi-core",
    "uwsgi-plugin-python3",
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
    # - Nodejs
    "npm",
    "nodeenv",
    "yarnpkg",
]


def setup_system() -> None:
    """Sets up the base system."""
    setup_base_system()
    # setup_hop3()
    # setup_uwsgi()
    # setup_acme()
    # setup_nginx()


def setup_base_system() -> None:
    """Sets up the base system environment by adding a user, installing
    packages, and creating necessary symlinks."""
    user(
        name="Add hop3 user",
        user=HOP3_USER,
        home=HOME_DIR,
        shell="/bin/bash",
        group="www-data",
    )

    # Install necessary Debian packages and update package lists if needed
    packages(
        name="Install Debian Packages",
        packages=PACKAGES,
        update=True,
    )

    # Create symlink for the node binary to ensure it is accessible from /usr/local/bin
    link(
        name="Create /usr/local/bin/node symlink",
        path="/usr/local/bin/node",
        target="/usr/bin/nodejs",
    )

    # Create symlink for the yarn binary to ensure it is accessible from /usr/local/bin
    link(
        name="Create /usr/local/bin/yarn symlink",
        path="/usr/local/bin/yarn",
        target="/usr/bin/yarnpkg",
    )


#
# Library
#
def user(name, user, home, shell, group) -> None:
    """Create or manage a system user account.

    Input:
    - name: The name of the user account to create or manage.
    - user: The username associated with the user account.
    - home: The home directory for the user.
    - shell: The default shell for the user account.
    - group: The primary group for the user account.
    """


def packages(name, packages, update) -> None:
    """Manage software packages on a system.

    This is intended to handle the installation, removal, or update
    of software packages on a computer system.

    Input:
    - name: A string representing the name of the package manager to use.
    - packages: A list of strings where each string is the name of a package to be managed.
    - update: A boolean indicating whether to update the packages.
    """


def link(name, path, target) -> None:
    """Creates a symbolic link.

    Input:
    - name: The name associated with the symbolic link (not used in the function, but could be for identification).
    - path: The file path where the symbolic link should be created.
    - target: The target file or directory that the symbolic link points to.
    """
    os.symlink(target, path)
