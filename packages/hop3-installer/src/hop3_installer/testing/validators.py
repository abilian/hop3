# Copyright (c) 2025-2026, Abilian SAS
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

    # Try running version (a local command that doesn't need server config)
    result = backend.run("~/.hop3-cli/venv/bin/hop3 version 2>&1")
    if result.success or "hop3" in result.stdout.lower():
        log_success("CLI command runs successfully")
    else:
        log_warning("CLI command returned an error when running 'version':")
        if result.stdout.strip():
            print(f"  stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            print(f"  stderr: {result.stderr.strip()}")
        if not result.stdout.strip() and not result.stderr.strip():
            print(f"  (no output, exit code: {result.returncode})")

    return all_passed


def _validate_hop3_service(backend: Backend) -> bool:
    """Validate hop3-server systemd service status.

    Returns:
        True (service status is advisory, not critical).
    """
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

    return True  # Service status is advisory


def _validate_postgresql(backend: Backend) -> bool:
    """Validate PostgreSQL installation and configuration.

    Returns:
        True if all PostgreSQL checks pass, False otherwise.
    """
    all_ok = True

    result = backend.run("systemctl is-active postgresql 2>/dev/null")
    if "active" in result.stdout:
        log_success("PostgreSQL service is running")
    else:
        log_error("PostgreSQL service is not running")
        all_ok = False

    result = backend.run(
        """su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_roles WHERE rolname='hop3'\\"" """
    )
    if "1" in result.stdout:
        log_success("PostgreSQL hop3 role exists")
    else:
        log_error("PostgreSQL hop3 role not found")
        all_ok = False

    result = backend.run(
        """su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_database WHERE datname='hop3'\\"" """
    )
    if "1" in result.stdout:
        log_success("PostgreSQL hop3 database exists")
    else:
        log_error("PostgreSQL hop3 database not found")
        all_ok = False

    return all_ok


def _validate_nginx(backend: Backend) -> bool:
    """Validate nginx installation and configuration.

    Returns:
        True if all nginx checks pass, False otherwise.
    """
    all_ok = True

    result = backend.run("systemctl is-active nginx 2>/dev/null")
    if "active" in result.stdout:
        log_success("nginx service is running")
    else:
        log_error("nginx service is not running")
        all_ok = False

    result = backend.run(
        "test -f /etc/nginx/sites-available/hop3 || test -f /etc/nginx/conf.d/hop3.conf"
    )
    if result.success:
        log_success("nginx hop3 config exists")
    else:
        log_error("nginx hop3 config not found")
        all_ok = False

    result = backend.run(
        "test -f /etc/hop3/ssl/hop3.crt && test -f /etc/hop3/ssl/hop3.key"
    )
    if result.success:
        log_success("SSL certificate exists")
    else:
        log_error("SSL certificate not found")
        all_ok = False

    result = backend.run("nginx -t 2>&1")
    if result.success:
        log_success("nginx configuration is valid")
    else:
        log_error("nginx configuration is invalid")
        if common.VERBOSE:
            print(result.stdout)
            print(result.stderr)
        all_ok = False

    return all_ok


def _validate_systemd_services(backend: Backend) -> bool:
    """Validate all systemd-dependent services.

    Returns:
        True if all services are properly configured, False otherwise.
    """
    all_ok = True

    _validate_hop3_service(backend)  # Advisory only

    if not _validate_postgresql(backend):
        all_ok = False

    if not _validate_nginx(backend):
        all_ok = False

    return all_ok


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

    # Check hop3-server command exists
    result = backend.run("test -f /home/hop3/venv/bin/hop3-server", sudo=True)
    if result.success:
        log_success("hop3-server command installed")
    else:
        log_error("hop3-server command not found")
        all_passed = False

    # Check systemd services (only if backend supports it)
    if backend.supports_systemd:
        if not _validate_systemd_services(backend):
            all_passed = False
    else:
        log_info("Skipping systemd checks (not supported by this backend)")

    return all_passed
