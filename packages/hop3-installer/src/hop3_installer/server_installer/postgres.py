# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL configuration."""

from __future__ import annotations

import secrets
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

from .config import HOP3_USER, ServerInstallerConfig


def setup_postgres(config: ServerInstallerConfig, distro: str) -> str | None:
    """Configure PostgreSQL.

    Returns:
        The generated postgres superuser password, or None if skipped.
    """
    if config.skip_postgres:
        print_info("Skipping PostgreSQL setup (--skip-postgres)")
        return None

    # Initialize PostgreSQL on Fedora
    if distro == "fedora":
        if not Path("/var/lib/pgsql/data/pg_hba.conf").exists():
            run_cmd(["postgresql-setup", "--initdb"], check=False)

    run_cmd(["systemctl", "enable", "postgresql"], check=False)
    run_cmd(["systemctl", "start", "postgresql"], check=False)

    # Create role and database
    try:
        run_cmd(
            ["su", "-", "postgres", "-c", f"createuser --createdb {HOP3_USER}"],
            check=False,
        )
        run_cmd(
            ["su", "-", "postgres", "-c", f"createdb -O {HOP3_USER} hop3"],
            check=False,
        )
        print_success("PostgreSQL role and database created")
    except CommandError:
        print_info("PostgreSQL role/database may already exist")

    # Set a password for postgres superuser
    pg_password = "hop3_" + secrets.token_hex(16)

    # Use psql to set the password
    sql_cmd = f"ALTER USER postgres PASSWORD '{pg_password}';"
    result = run_cmd(
        ["su", "-", "postgres", "-c", f'psql -c "{sql_cmd}"'],
        check=False,
    )
    if result.returncode == 0:
        print_success("PostgreSQL superuser password configured")
    else:
        print_warning("Could not set PostgreSQL superuser password")
        return None

    return pg_password
