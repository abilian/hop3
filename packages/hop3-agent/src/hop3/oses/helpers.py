# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import subprocess
from io import StringIO
from pathlib import Path


class Platform:
    """A class representing a software or hardware platform.

    This is intended to serve as a base for creating specific platform
    implementations. Currently, it does not contain any attributes or
    methods.
    """


class Linux(Platform):
    def put_file(self, name, src, dest, *, mode=None, owner=None, group=None) -> None:
        """Copies the content of a file or file-like object to a destination
        path.

        Inputs:
        - name: The name of the file to be copied.
        - src: The source, which can be a Path object, a string representing a file path, or a StringIO object.
        - dest: The destination file path where the content will be written.
        - mode: (Optional) File mode to be set on the destination file.
        - owner: (Optional) Owner to be set for the destination file.
        - group: (Optional) Group to be set for the destination file.
        """
        match src:
            case Path():
                # If src is a Path object, read its content and write to dest
                Path(dest).write_text(src.read_text())
            case str():
                # If src is a string path, convert it to a Path object, read its content and write to dest
                Path(dest).write_text(Path(src).read_text())
            case StringIO():
                # If src is a StringIO object, get its content and write to dest
                Path(dest).write_text(src.getvalue())
            case _:
                # If src is of an unsupported type, raise a ValueError
                msg = "Invalid src type"
                raise ValueError(msg)

        # TODO: mode, owner, group

    def ensure_user(self, name, user, home, shell, group) -> None:
        """Ensure that a user account is set up on the system with the
        specified attributes.

        Input:
        - name: The display name of the user.
        - user: The username for the account.
        - home: The home directory for the user.
        - shell: The default shell for the user.
        - group: The primary group for the user account.
        """

    # server.user(
    #     name="Add hop3 user",
    #     user=HOP3_USER,
    #     home=HOME_DIR,
    #     shell="/bin/bash",
    #     group="www-data",
    # )

    def ensure_link(self, name, path, target) -> None:
        """Ensure that a symbolic link is created.

        Input:
        - name: A descriptive name for the link operation (not used in actual logic).
        - path: The source path that the symbolic link will point to.
        - target: The destination path for the symbolic link.
        """
        os.symlink(path, target)


class Debian(Linux):
    def ensure_packages(self, name, packages, *, update=True) -> None:
        """Ensure that a list of packages is installed using the system's
        package manager.

        Input:
        - name: A string representing the name for logging or identification purposes.
        - packages: A list of strings where each string is the name of a package to be installed.
        - update: A boolean flag indicating whether to update the package list before installation (default is True).
        """

        packages_str = " ".join(packages)
        cmd = f"apt-get install -y {packages_str}"
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
