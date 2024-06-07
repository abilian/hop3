# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import os
import subprocess
from io import StringIO
from pathlib import Path


class Platform:
    pass


class Linux(Platform):
    def put_file(self, name, src, dest, *, mode=None, owner=None, group=None):
        match src:
            case Path():
                Path(dest).write_text(src.read_text())
            case str():
                Path(dest).write_text(Path(src).read_text())
            case StringIO():
                Path(dest).write_text(src.getvalue())
            case _:
                raise ValueError("Invalid src type")

        # TODO: mode, owner, group

    def ensure_user(self, name, user, home, shell, group):
        pass

    # server.user(
    #     name="Add hop3 user",
    #     user=HOP3_USER,
    #     home=HOME_DIR,
    #     shell="/bin/bash",
    #     group="www-data",
    # )

    def ensure_link(self, name, path, target):
        os.symlink(path, target)


class Debian(Linux):
    def ensure_packages(self, name, packages, *, update=True):
        packages_str = " ".join(packages)
        shell(f"apt-get install -y {packages_str}")


def shell(cmd):
    return subprocess.run(cmd, shell=True, check=True, capture_output=True)
