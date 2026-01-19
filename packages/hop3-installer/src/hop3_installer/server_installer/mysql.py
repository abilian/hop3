# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""MySQL configuration."""

from __future__ import annotations

import secrets
import subprocess  # noqa: TC003
from pathlib import Path

from hop3_installer.common import (
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

from .config import ServerInstallerConfig  # noqa: TC001


def _get_debian_mysql_credentials() -> tuple[str, str] | None:
    """Get MySQL credentials from Debian maintenance file.

    On Debian/Ubuntu, /etc/mysql/debian.cnf contains credentials for
    the debian-sys-maint user which has full privileges.

    Returns:
        Tuple of (user, password) or None if not available.
    """
    debian_cnf = Path("/etc/mysql/debian.cnf")
    if not debian_cnf.exists():
        return None

    try:
        content = debian_cnf.read_text()
        user = None
        password = None
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("user"):
                user = line.split("=")[1].strip()
            elif line.startswith("password"):
                password = line.split("=")[1].strip()
            if user and password:
                return (user, password)
    except Exception:
        pass
    return None


def _start_mysql_service() -> bool:
    """Start MySQL or MariaDB service.

    Returns:
        True if service started successfully, False otherwise.
    """
    run_cmd(["systemctl", "enable", "mysql"], check=False)
    result = run_cmd(["systemctl", "start", "mysql"], check=False)

    if result.returncode != 0:
        # Try mariadb service name (some distros use this)
        run_cmd(["systemctl", "enable", "mariadb"], check=False)
        result = run_cmd(["systemctl", "start", "mariadb"], check=False)

    return result.returncode == 0


def _find_mysql_admin_connection() -> list[str] | None:
    """Find a working MySQL admin connection method.

    Tries various methods to connect to MySQL as an admin user.

    Returns:
        Command list that works, or None if no method works.
    """
    # Build list of commands to try
    test_commands: list[list[str]] = [
        ["mysql"],  # Socket auth as current user (root)
        ["sudo", "mysql"],  # Socket auth via sudo
        ["mysql", "-u", "root"],  # Traditional root
    ]

    # Also try Debian maintenance user if available
    debian_creds = _get_debian_mysql_credentials()
    if debian_creds:
        user, password = debian_creds
        test_commands.insert(0, ["mysql", f"-u{user}", f"-p{password}"])

    for test_cmd in test_commands:
        result = run_cmd(test_cmd + ["-e", "SELECT 1;"], check=False)
        if result.returncode == 0:
            # Don't show password in logs
            display_cmd = " ".join(test_cmd)
            if debian_creds and debian_creds[1] in display_cmd:
                display_cmd = display_cmd.replace(debian_creds[1], "***")
            print_detail(f"MySQL admin access via: {display_cmd}")
            return test_cmd

    return None


def _validate_mysql_password(password: str) -> bool:
    """Validate that password contains only safe characters for SQL.

    This is a defensive measure against SQL injection in case the password
    generation method ever changes. Currently passwords are generated via
    secrets.token_hex() which only produces hex characters (0-9, a-f).

    Args:
        password: Password to validate.

    Returns:
        True if password is safe, False otherwise.
    """
    # Allow alphanumeric, underscore, and hyphen (common in generated passwords)
    allowed_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    )
    return all(c in allowed_chars for c in password)


def _create_mysql_hop3_user(root_cmd: list[str], mysql_password: str) -> bool:
    """Create hop3 MySQL user with privileges.

    Args:
        root_cmd: Working MySQL admin command.
        mysql_password: Password to set for hop3 user.

    Returns:
        True if user created successfully, False otherwise.
    """
    # Validate password to prevent SQL injection
    if not _validate_mysql_password(mysql_password):
        print_warning("Invalid characters in MySQL password")
        return False

    def run_sql(sql: str) -> subprocess.CompletedProcess:
        return run_cmd(root_cmd + ["-e", sql], check=False)

    # Drop existing hop3 user if exists (clean slate)
    # Note: MySQL treats 'localhost' (socket) and '127.0.0.1' (TCP) as different hosts
    run_sql("DROP USER IF EXISTS 'hop3'@'localhost';")
    run_sql("DROP USER IF EXISTS 'hop3'@'127.0.0.1';")

    # Create hop3 user with password authentication for both localhost and 127.0.0.1
    # Use mysql_native_password for compatibility with mysql-connector-python
    result = run_sql(
        f"CREATE USER 'hop3'@'localhost' IDENTIFIED WITH mysql_native_password BY '{mysql_password}';"
    )
    if result.returncode != 0:
        print_warning("Failed to create MySQL user 'hop3'@'localhost'")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    result = run_sql(
        f"CREATE USER 'hop3'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY '{mysql_password}';"
    )
    if result.returncode != 0:
        print_warning("Failed to create MySQL user 'hop3'@'127.0.0.1'")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    # Grant all privileges to both hosts
    result = run_sql(
        "GRANT ALL PRIVILEGES ON *.* TO 'hop3'@'localhost' WITH GRANT OPTION;"
    )
    if result.returncode != 0:
        print_warning("Failed to grant privileges to hop3@localhost")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    result = run_sql(
        "GRANT ALL PRIVILEGES ON *.* TO 'hop3'@'127.0.0.1' WITH GRANT OPTION;"
    )
    if result.returncode != 0:
        print_warning("Failed to grant privileges to hop3@127.0.0.1")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    run_sql("FLUSH PRIVILEGES;")
    return True


def _verify_mysql_hop3_connection(mysql_password: str) -> bool:
    """Verify hop3 user can connect to MySQL.

    Args:
        mysql_password: Password for hop3 user.

    Returns:
        True if connection verified, False otherwise.
    """
    result = run_cmd(
        [
            "mysql",
            "-u",
            "hop3",
            f"-p{mysql_password}",
            "-h",
            "127.0.0.1",
            "-e",
            "SELECT 1;",
        ],
        check=False,
    )

    if result.returncode != 0:
        print_warning("MySQL user created but connection verification failed")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    return True


def setup_mysql(config: ServerInstallerConfig, distro: str) -> str | None:
    """Configure MySQL.

    Returns:
        The generated MySQL password for hop3 user, or None if skipped/failed.
    """
    if not config.with_mysql:
        return None

    print_info("Configuring MySQL...")

    # Start MySQL service
    if not _start_mysql_service():
        print_warning("Could not start MySQL service")
        return None
    print_success("MySQL service started")

    # Find a working admin connection
    mysql_root_cmd = _find_mysql_admin_connection()

    if mysql_root_cmd is None:
        print_warning("Could not connect to MySQL as admin")
        print_detail("Please check MySQL is running and has default authentication")
        print_detail("You may need to configure MySQL manually")
        return None

    # Generate a secure password
    mysql_password = "hop3_" + secrets.token_hex(16)

    # Create hop3 user with privileges
    if not _create_mysql_hop3_user(mysql_root_cmd, mysql_password):
        return None
    print_success("MySQL user 'hop3' created with privileges")

    # Verify the connection works
    if not _verify_mysql_hop3_connection(mysql_password):
        return None

    print_success("MySQL connection verified successfully")
    return mysql_password
