# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL configuration."""

from __future__ import annotations

import secrets
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

from .config import HOP3_USER, ServerInstallerConfig


def _start_postgres_service(distro: str) -> bool:
    """Start PostgreSQL service.

    Args:
        distro: Distribution name.

    Returns:
        True if service started successfully.
    """
    # Initialize PostgreSQL on Fedora (required before first start)
    if distro == "fedora":
        if not Path("/var/lib/pgsql/data/pg_hba.conf").exists():
            result = run_cmd(["postgresql-setup", "--initdb"], check=False)
            if result.returncode != 0:
                print_warning("PostgreSQL initialization failed")
                if result.stderr:
                    print_detail(result.stderr[:200])

    result = run_cmd(["systemctl", "enable", "postgresql"], check=False)
    if result.returncode != 0:
        print_warning("Failed to enable PostgreSQL service")

    result = run_cmd(["systemctl", "start", "postgresql"], check=False)

    if result.returncode != 0:
        print_warning("Could not start PostgreSQL service")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    return True


def _create_postgres_role_and_db() -> bool:
    """Create hop3 PostgreSQL role and database.

    Returns:
        True if created successfully (or already exists).
    """
    try:
        # Create role (--createdb allows it to create databases for apps)
        result = run_cmd(
            ["su", "-", "postgres", "-c", f"createuser --createdb {HOP3_USER}"],
            check=False,
        )
        if result.returncode != 0 and "already exists" not in (result.stderr or ""):
            print_detail(f"createuser result: {result.stderr or result.stdout}")

        # Create default database
        result = run_cmd(
            ["su", "-", "postgres", "-c", f"createdb -O {HOP3_USER} hop3"],
            check=False,
        )
        if result.returncode != 0 and "already exists" not in (result.stderr or ""):
            print_detail(f"createdb result: {result.stderr or result.stdout}")

        print_success("PostgreSQL role and database created")
        return True
    except CommandError as e:
        print_warning(f"PostgreSQL role/database creation issue: {e}")
        return False


def _set_postgres_password() -> str | None:
    """Set a password for postgres superuser.

    Returns:
        The generated password, or None if failed.
    """
    pg_password = "hop3_" + secrets.token_hex(16)

    sql_cmd = f"ALTER USER postgres PASSWORD '{pg_password}';"
    result = run_cmd(
        ["su", "-", "postgres", "-c", f'psql -c "{sql_cmd}"'],
        check=False,
    )

    if result.returncode != 0:
        print_warning("Could not set PostgreSQL superuser password")
        if result.stderr:
            print_detail(result.stderr[:200])
        return None

    print_success("PostgreSQL superuser password configured")
    return pg_password


def _verify_postgres_connection() -> bool:
    """Verify PostgreSQL connection works for hop3 user.

    Returns:
        True if connection verified successfully.
    """
    # Test connection as hop3 user via peer authentication
    result = run_cmd(
        ["su", "-", HOP3_USER, "-c", "psql -d hop3 -c 'SELECT 1;'"],
        check=False,
    )

    if result.returncode != 0:
        print_warning("PostgreSQL connection verification failed")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    print_success("PostgreSQL connection verified")
    return True


def setup_postgres(config: ServerInstallerConfig, distro: str) -> str | None:
    """Configure PostgreSQL.

    Returns:
        The generated postgres superuser password, or None if skipped/failed.
    """
    if config.skip_postgres:
        print_info("Skipping PostgreSQL setup (--skip-postgres)")
        return None

    print_info("Configuring PostgreSQL...")

    # Start service
    if not _start_postgres_service(distro):
        return None
    print_success("PostgreSQL service started")

    # Create role and database
    if not _create_postgres_role_and_db():
        print_warning(
            "PostgreSQL role/database creation had issues - continuing anyway"
        )

    # Set superuser password
    pg_password = _set_postgres_password()
    if pg_password is None:
        return None

    # Verify connection
    if not _verify_postgres_connection():
        print_warning("PostgreSQL setup completed but verification failed")
        # Still return the password - the setup might be usable

    return pg_password
