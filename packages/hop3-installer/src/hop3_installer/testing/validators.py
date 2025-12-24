# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Validation functions for installer tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import common
from .common import log_error, log_info, log_success, log_warning

if TYPE_CHECKING:
    from .backends.base import Backend


def validate_cli_installation(backend: Backend) -> bool:
    """Validate CLI installation using the provided backend.

    Args:
        backend: The test backend to use

    Returns:
        True if all validations pass, False otherwise
    """
    log_info("Validating CLI installation...")
    all_passed = True

    # Check venv exists
    result = backend.run("test -d ~/.hop3-cli/venv")
    if result.success:
        log_success("Virtual environment exists")
    else:
        log_error("Virtual environment not found")
        all_passed = False

    # Check hop3 command exists
    result = backend.run(
        "test -f ~/.hop3-cli/venv/bin/hop3 || test -f ~/.hop3-cli/venv/bin/hop"
    )
    if result.success:
        log_success("CLI command installed")
    else:
        log_error("CLI command not found")
        all_passed = False

    # Check symlink
    result = backend.run("test -L ~/.local/bin/hop3 || test -f ~/.local/bin/hop3")
    if result.success:
        log_success("Symlink created")
    else:
        log_warning("Symlink not found (may be expected with --no-modify-path)")

    # Try running help
    result = backend.run(
        "~/.hop3-cli/venv/bin/hop3 --help 2>&1 || ~/.hop3-cli/venv/bin/hop --help 2>&1"
    )
    if result.success or "usage" in result.stdout.lower():
        log_success("CLI command runs successfully")
    else:
        log_warning("CLI command returned an error when running --help:")
        if result.stdout.strip():
            print(f"  stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            print(f"  stderr: {result.stderr.strip()}")
        if not result.stdout.strip() and not result.stderr.strip():
            print(f"  (no output, exit code: {result.returncode})")

    return all_passed


def validate_server_installation(backend: Backend) -> bool:
    """Validate server installation using the provided backend.

    Args:
        backend: The test backend to use

    Returns:
        True if all validations pass, False otherwise
    """
    log_info("Validating server installation...")
    all_passed = True

    # Check hop3 user exists
    result = backend.run("id hop3")
    if result.success:
        log_success("hop3 user exists")
    else:
        log_error("hop3 user not found")
        all_passed = False

    # Check venv exists
    result = backend.run("test -d /home/hop3/venv", sudo=True)
    if result.success:
        log_success("Virtual environment exists")
    else:
        log_error("Virtual environment not found")
        all_passed = False

    # Check hop-server command exists
    result = backend.run("test -f /home/hop3/venv/bin/hop-server", sudo=True)
    if result.success:
        log_success("hop-server command installed")
    else:
        log_error("hop-server command not found")
        all_passed = False

    # Check systemd service (only if backend supports it)
    if backend.supports_systemd:
        result = backend.run("systemctl is-enabled hop3-server 2>/dev/null")
        if "enabled" in result.stdout:
            log_success("hop3-server service is enabled")
        else:
            log_warning("hop3-server service not enabled")

        result = backend.run("systemctl is-active hop3-server 2>/dev/null")
        if "active" in result.stdout:
            log_success("hop3-server service is running")
        else:
            log_warning("hop3-server service is not running (may need configuration)")

        # Check PostgreSQL
        result = backend.run("systemctl is-active postgresql 2>/dev/null")
        if "active" in result.stdout:
            log_success("PostgreSQL service is running")
        else:
            log_error("PostgreSQL service is not running")
            all_passed = False

        # Check PostgreSQL hop3 role exists
        result = backend.run(
            """su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_roles WHERE rolname='hop3'\\"" """
        )
        if "1" in result.stdout:
            log_success("PostgreSQL hop3 role exists")
        else:
            log_error("PostgreSQL hop3 role not found")
            all_passed = False

        # Check PostgreSQL hop3 database exists
        result = backend.run(
            """su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_database WHERE datname='hop3'\\"" """
        )
        if "1" in result.stdout:
            log_success("PostgreSQL hop3 database exists")
        else:
            log_error("PostgreSQL hop3 database not found")
            all_passed = False

        # Check nginx is running
        result = backend.run("systemctl is-active nginx 2>/dev/null")
        if "active" in result.stdout:
            log_success("nginx service is running")
        else:
            log_error("nginx service is not running")
            all_passed = False

        # Check nginx config exists
        result = backend.run(
            "test -f /etc/nginx/sites-available/hop3 || test -f /etc/nginx/conf.d/hop3.conf"
        )
        if result.success:
            log_success("nginx hop3 config exists")
        else:
            log_error("nginx hop3 config not found")
            all_passed = False

        # Check SSL certificate exists
        result = backend.run(
            "test -f /etc/hop3/ssl/hop3.crt && test -f /etc/hop3/ssl/hop3.key"
        )
        if result.success:
            log_success("SSL certificate exists")
        else:
            log_error("SSL certificate not found")
            all_passed = False

        # Verify nginx config is valid
        result = backend.run("nginx -t 2>&1")
        if result.success:
            log_success("nginx configuration is valid")
        else:
            log_error("nginx configuration is invalid")
            if common.VERBOSE:
                print(result.stdout)
                print(result.stderr)
            all_passed = False
    else:
        log_info("Skipping systemd checks (not supported by this backend)")

    return all_passed
