# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""User and group management for server installer."""

from __future__ import annotations

import grp
import os
import pwd
import subprocess  # noqa: TC003
from pathlib import Path

from hop3_installer.common import print_info, print_success, print_warning, run_cmd

from .config import HOME_DIR, HOP3_GROUP, HOP3_USER


def user_exists(username: str) -> bool:
    """Check if a user exists."""
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def group_exists(groupname: str) -> bool:
    """Check if a group exists."""
    try:
        grp.getgrnam(groupname)
        return True
    except KeyError:
        return False


def run_as_hop3(cmd: str) -> subprocess.CompletedProcess:
    """Run a command as the hop3 user."""
    return run_cmd(["su", "-", HOP3_USER, "-c", cmd])


def create_user_and_group() -> None:
    """Create the hop3 user and group."""
    # Create group
    if not group_exists(HOP3_GROUP):
        run_cmd(["groupadd", HOP3_GROUP])
        print_success(f"Created group: {HOP3_GROUP}")
    else:
        print_info(f"Group {HOP3_GROUP} already exists")

    # Create user
    if not user_exists(HOP3_USER):
        run_cmd([
            "useradd",
            "-m",
            "-g",
            HOP3_GROUP,
            "-s",
            "/bin/bash",
            "-d",
            str(HOME_DIR),
            HOP3_USER,
        ])
        print_success(f"Created user: {HOP3_USER}")
    else:
        print_info(f"User {HOP3_USER} already exists")

    # Ensure home directory exists with correct permissions
    if not HOME_DIR.exists():
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        print_info(f"Created home directory: {HOME_DIR}")

    hop3_uid = pwd.getpwnam(HOP3_USER).pw_uid
    hop3_gid = grp.getgrnam(HOP3_GROUP).gr_gid
    os.chown(HOME_DIR, hop3_uid, hop3_gid)
    Path(HOME_DIR).chmod(0o755)

    # Add www-data to hop3 group (needed for nginx to access app sockets)
    if user_exists("www-data"):
        result = run_cmd(["usermod", "-a", "-G", HOP3_GROUP, "www-data"], check=False)
        if result.returncode == 0:
            print_info("Added www-data to hop3 group")
        else:
            print_warning(
                "Failed to add www-data to hop3 group - nginx may have permission issues"
            )
