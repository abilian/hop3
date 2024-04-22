# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

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
]


def setup_system() -> None:
    setup_base_system()
    # setup_hop3()
    # setup_uwsgi()
    # setup_acme()
    # setup_nginx()


def setup_base_system() -> None:
    user(
        name="Add hop3 user",
        user=HOP3_USER,
        home=HOME_DIR,
        shell="/bin/bash",
        group="www-data",
    )

    packages(
        name="Install Debian Packages",
        packages=PACKAGES,
        update=True,
    )
    link(
        name="Create /usr/local/bin/node symlink",
        path="/usr/local/bin/node",
        target="/usr/bin/nodejs",
    )
    link(
        name="Create /usr/local/bin/yarn symlink",
        path="/usr/local/bin/yarn",
        target="/usr/bin/yarnpkg",
    )


#
# Library
#
def user(name, user, home, shell, group) -> None:
    pass


def packages(name, packages, update) -> None:
    pass


def link(name, path, target) -> None:
    os.symlink(target, path)
