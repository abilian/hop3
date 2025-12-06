# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Command execution helpers for demos."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from lib.output import Colors, get_output_level, print_command, print_error

if TYPE_CHECKING:
    from lib.context import DemoContext


class CommandError(Exception):
    """Raised when a command fails."""

    def __init__(self, message: str, returncode: int = 1):
        super().__init__(message)
        self.returncode = returncode


def run_local(
    cmd: str, *, show: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a command locally."""
    if show and get_output_level() >= 2:  # NORMAL or VERBOSE
        print_command(cmd)
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print_error(f"Command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}", file=sys.stderr)
        raise CommandError(f"Command failed: {cmd}", result.returncode)
    return result


def run_ssh(
    ctx: DemoContext, cmd: str, *, show: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a command on the remote server via SSH."""
    ssh_cmd = f'ssh -o StrictHostKeyChecking=accept-new {ctx.ssh_target} "{cmd}"'
    if show and get_output_level() >= 2:  # NORMAL or VERBOSE
        print_command(f"ssh {ctx.ssh_target} '{cmd}'")
    result = subprocess.run(
        ssh_cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print_error(f"SSH command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}", file=sys.stderr)
        raise CommandError(f"SSH command failed: {cmd}", result.returncode)
    return result


def run_hop3(
    cmd: str, *, show: bool = True, check: bool = True, quiet: bool = False
) -> subprocess.CompletedProcess:
    """Run a hop3 CLI command.

    Args:
        cmd: The hop3 command to run (without 'hop3' prefix)
        show: Whether to show the command being run
        check: Whether to raise on failure
        quiet: If True, suppress stdout output regardless of global level
    """
    full_cmd = f"hop3 {cmd}"
    output_level = get_output_level()

    if show and output_level >= 2:  # NORMAL or VERBOSE
        print_command(full_cmd)

    result = subprocess.run(
        full_cmd, shell=True, capture_output=True, text=True, check=False
    )

    # Only print stdout in NORMAL or VERBOSE mode, and not if quiet=True
    if result.stdout and output_level >= 2 and not quiet:
        print(result.stdout)

    if check and result.returncode != 0:
        print_error(f"hop3 command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}", file=sys.stderr)
        raise CommandError(f"hop3 command failed: {cmd}", result.returncode)
    return result
