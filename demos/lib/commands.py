# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Command execution helpers for demos."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from .output import Colors, print_command, print_error

if TYPE_CHECKING:
    from .context import DemoContext


def run_local(
    cmd: str, *, show: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a command locally."""
    if show:
        print_command(cmd)
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print_error(f"Command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
        sys.exit(1)
    return result


def run_ssh(
    ctx: DemoContext, cmd: str, *, show: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a command on the remote server via SSH."""
    ssh_cmd = f'ssh -o StrictHostKeyChecking=accept-new {ctx.ssh_target} "{cmd}"'
    if show:
        print_command(f"ssh {ctx.ssh_target} '{cmd}'")
    result = subprocess.run(
        ssh_cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print_error(f"SSH command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
        sys.exit(1)
    return result


def run_hop3(
    cmd: str, *, show: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a hop3 CLI command."""
    full_cmd = f"hop3 {cmd}"
    if show:
        print_command(full_cmd)
    result = subprocess.run(
        full_cmd, shell=True, capture_output=True, text=True, check=False
    )
    if result.stdout:
        print(result.stdout)
    if check and result.returncode != 0:
        print_error(f"hop3 command failed with exit code {result.returncode}")
        if result.stderr:
            print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
        sys.exit(1)
    return result
