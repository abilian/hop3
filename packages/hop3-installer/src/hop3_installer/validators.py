# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Validation functions for Hop3 installations.

This module provides validation functions that can be used:
1. As post-install self-tests by the installers
2. By E2E tests via the backend abstraction

The validators accept a `runner` callable that executes commands and returns
a CommandResult. This allows the same validation logic to work both locally
(for self-tests) and remotely (for E2E tests via SSH/Docker).
"""

from __future__ import annotations

import subprocess
from typing import Protocol

from .common import (
    Colors,
    CommandResult,
    print_error,
    print_info,
    print_success,
    print_warning,
)

__all__ = [
    "CommandRunner",
    "LocalRunner",
    "validate_cli_installation",
    "validate_server_installation",
]


# =============================================================================
# Command Runner Protocol
# =============================================================================


class CommandRunner(Protocol):
    """Protocol for command execution.

    Implementations can run commands locally (LocalRunner) or remotely
    (via SSH, Docker, etc. in test backends).
    """

    def __call__(self, command: str, *, sudo: bool = False) -> CommandResult:
        """Execute a command and return the result.

        Args:
            command: Shell command to execute
            sudo: Whether to run with sudo

        Returns:
            CommandResult with returncode, stdout, stderr
        """
        ...


class LocalRunner:
    """Run commands locally via subprocess.

    Used for post-install self-tests on the local system.
    """

    def __init__(self, *, verbose: bool = False):
        self.verbose = verbose

    def __call__(self, command: str, *, sudo: bool = False) -> CommandResult:
        """Execute a command locally."""
        if sudo:
            command = f"sudo {command}"

        if self.verbose:
            print(f"  {Colors.DIM}[CMD]{Colors.RESET} {command}")

        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            check=False,
        )

        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )


# =============================================================================
# CLI Validation
# =============================================================================


def validate_cli_installation(runner: CommandRunner) -> bool:
    """Validate CLI installation.

    Args:
        runner: Command runner (LocalRunner for self-test, Backend.run for E2E)

    Returns:
        True if all validations pass, False otherwise
    """
    print_info("Validating CLI installation...")
    all_passed = True

    # Check venv exists
    result = runner("test -d ~/.hop3-cli/venv")
    if result.success:
        print_success("Virtual environment exists")
    else:
        print_error("Virtual environment not found")
        all_passed = False

    # Check hop3 command exists
    result = runner(
        "test -f ~/.hop3-cli/venv/bin/hop3 || test -f ~/.hop3-cli/venv/bin/hop"
    )
    if result.success:
        print_success("CLI command installed")
    else:
        print_error("CLI command not found")
        all_passed = False

    # Check symlink
    result = runner("test -L ~/.local/bin/hop3 || test -f ~/.local/bin/hop3")
    if result.success:
        print_success("Symlink created")
    else:
        print_warning("Symlink not found (may be expected with --no-modify-path)")

    # Try running version (a local command that doesn't need server config)
    result = runner("~/.hop3-cli/venv/bin/hop3 version 2>&1")
    if result.success or "hop3" in result.stdout.lower():
        print_success("CLI command runs successfully")
    else:
        print_warning("CLI command returned an error when running 'version':")
        if result.stdout.strip():
            print(f"        stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            print(f"        stderr: {result.stderr.strip()}")
        if not result.stdout.strip() and not result.stderr.strip():
            print(f"        (no output, exit code: {result.returncode})")

    return all_passed


# =============================================================================
# Server Validation
# =============================================================================


def _validate_hop3_service(runner: CommandRunner) -> bool:
    """Validate hop3-server systemd service status.

    Returns:
        True (service status is advisory, not critical).
    """
    result = runner("systemctl is-enabled hop3-server 2>/dev/null")
    if "enabled" in result.stdout:
        print_success("hop3-server service is enabled")
    else:
        print_warning("hop3-server service not enabled")

    result = runner("systemctl is-active hop3-server 2>/dev/null")
    if "active" in result.stdout:
        print_success("hop3-server service is running")
    else:
        print_warning("hop3-server service is not running (may need configuration)")

    return True  # Service status is advisory


def _validate_postgresql(runner: CommandRunner) -> bool:
    """Validate PostgreSQL installation and configuration.

    Returns:
        True if all PostgreSQL checks pass, False otherwise.
    """
    all_ok = True

    result = runner("systemctl is-active postgresql 2>/dev/null")
    if "active" in result.stdout:
        print_success("PostgreSQL service is running")
    else:
        print_error("PostgreSQL service is not running")
        all_ok = False

    result = runner(
        """su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_roles WHERE rolname='hop3'\\"" """
    )
    if "1" in result.stdout:
        print_success("PostgreSQL hop3 role exists")
    else:
        print_error("PostgreSQL hop3 role not found")
        all_ok = False

    result = runner(
        """su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_database WHERE datname='hop3'\\"" """
    )
    if "1" in result.stdout:
        print_success("PostgreSQL hop3 database exists")
    else:
        print_error("PostgreSQL hop3 database not found")
        all_ok = False

    return all_ok


def _validate_nginx(runner: CommandRunner, *, verbose: bool = False) -> bool:
    """Validate nginx installation and configuration.

    Returns:
        True if all nginx checks pass, False otherwise.
    """
    all_ok = True

    result = runner("systemctl is-active nginx 2>/dev/null")
    if "active" in result.stdout:
        print_success("nginx service is running")
    else:
        print_error("nginx service is not running")
        all_ok = False

    result = runner(
        "test -f /etc/nginx/sites-available/hop3 || test -f /etc/nginx/conf.d/hop3.conf"
    )
    if result.success:
        print_success("nginx hop3 config exists")
    else:
        print_error("nginx hop3 config not found")
        all_ok = False

    result = runner("test -f /etc/hop3/ssl/hop3.crt && test -f /etc/hop3/ssl/hop3.key")
    if result.success:
        print_success("SSL certificate exists")
    else:
        print_error("SSL certificate not found")
        all_ok = False

    result = runner("nginx -t 2>&1")
    if result.success:
        print_success("nginx configuration is valid")
    else:
        print_error("nginx configuration is invalid")
        if verbose:
            print(result.stdout)
            print(result.stderr)
        all_ok = False

    return all_ok


def _validate_systemd_services(runner: CommandRunner, *, verbose: bool = False) -> bool:
    """Validate all systemd-dependent services.

    Returns:
        True if all services are properly configured, False otherwise.
    """
    all_ok = True

    _validate_hop3_service(runner)  # Advisory only

    if not _validate_postgresql(runner):
        all_ok = False

    if not _validate_nginx(runner, verbose=verbose):
        all_ok = False

    return all_ok


def validate_server_installation(
    runner: CommandRunner,
    *,
    check_systemd: bool = True,
    verbose: bool = False,
) -> bool:
    """Validate server installation.

    Args:
        runner: Command runner (LocalRunner for self-test, Backend.run for E2E)
        check_systemd: Whether to check systemd services (disable for Docker without systemd)
        verbose: Show verbose output for failures

    Returns:
        True if all validations pass, False otherwise
    """
    print_info("Validating server installation...")
    all_passed = True

    # Check hop3 user exists
    result = runner("id hop3")
    if result.success:
        print_success("hop3 user exists")
    else:
        print_error("hop3 user not found")
        all_passed = False

    # Check venv exists
    result = runner("test -d /home/hop3/venv", sudo=True)
    if result.success:
        print_success("Virtual environment exists")
    else:
        print_error("Virtual environment not found")
        all_passed = False

    # Check hop3-server command exists
    result = runner("test -f /home/hop3/venv/bin/hop3-server", sudo=True)
    if result.success:
        print_success("hop3-server command installed")
    else:
        print_error("hop3-server command not found")
        all_passed = False

    # Check systemd services
    if check_systemd:
        if not _validate_systemd_services(runner, verbose=verbose):
            all_passed = False
    else:
        print_info("Skipping systemd checks (disabled)")

    return all_passed
