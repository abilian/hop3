# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""User and group management for server installer."""

from __future__ import annotations

import grp
import os
import pwd
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

from hop3_installer.common import print_info, print_success, print_warning, run_cmd
from hop3_installer.constants import HOME_DIR, HOP3_GROUP, HOP3_USER

from .redis import fix_redis_pass_ownership


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


def run_as_hop3(
    argv: Sequence[str],
    *,
    check: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """
    Run a command as the hop3 user.

    ``su -c`` hands its argument to a login shell, so this is a shell context
    whether or not the caller wants one. Taking an argv list and joining it
    here makes the quoting a property of the seam instead of a rule every call
    site has to remember -- see ``notes/security/security-model.md`` §3.2.5.

    Use :func:`run_as_hop3_shell` for the rare command that genuinely needs
    shell operators.

    Args:
        argv: Command and arguments. Quoted here; callers pass raw values.
            Declared ``Sequence[str]`` because a bare ``str`` IS one -- that is
            exactly the confusion the guard below rejects, and the annotation
            has to admit it for the check to mean anything.
        check: Whether to raise on non-zero exit (default: False).
        timeout: Timeout in seconds (default: None).

    Returns:
        CompletedProcess with stdout/stderr.

    Raises:
        TypeError: if handed a string instead of a list.
    """
    # A bare string is silent corruption, not a type nit: shlex.join iterates
    # it per character, so "pip install foo" becomes "p i p ' ' i n s t ...",
    # which still parses and still runs -- as the wrong command. Most callers
    # pass check=False, so the resulting failure would be swallowed. Fail loud.
    if isinstance(argv, str):
        msg = (
            f"run_as_hop3 takes a list of arguments, got a string: {argv!r}. "
            f"Use run_as_hop3([...]) for a command, or run_as_hop3_shell(...) "
            f"if it genuinely needs shell operators."
        )
        raise TypeError(msg)
    return run_as_hop3_shell(shlex.join(argv), check=check, timeout=timeout)


def run_as_hop3_shell(
    script: str,
    *,
    check: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """
    Run a shell script fragment as the hop3 user.

    Only for commands that need shell operators (``|``, ``&&``, redirection).
    **The caller owns the quoting**: any value interpolated into ``script``
    must be passed through :func:`shlex.quote` first. Prefer
    :func:`run_as_hop3`, which quotes for you, wherever the command is a plain
    argv.

    Args:
        script: Shell script fragment, executed by the hop3 user's login shell.
        check: Whether to raise on non-zero exit (default: False).
        timeout: Timeout in seconds (default: None).

    Returns:
        CompletedProcess with stdout/stderr.
    """
    return run_cmd(
        ["su", "-", HOP3_USER, "-c", script],
        check=check,
        timeout=timeout,
    )


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

    # Add hop3 to docker group (needed for Docker builds)
    if group_exists("docker"):
        result = run_cmd(["usermod", "-a", "-G", "docker", HOP3_USER], check=False)
        if result.returncode == 0:
            print_info("Added hop3 to docker group")
        else:
            print_warning("Failed to add hop3 to docker group - Docker builds may fail")

    # Re-apply ownership on /etc/hop3/redis-pass in case Redis was
    # configured before the hop3 group existed (first-run order).
    fix_redis_pass_ownership()
