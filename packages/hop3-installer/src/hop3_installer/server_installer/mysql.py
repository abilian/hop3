# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""MySQL configuration."""

from __future__ import annotations

import re
import secrets
import subprocess
from pathlib import Path

from hop3_installer.common import (
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

from .config import ServerInstallerConfig
from .docker_utils import get_docker_bridge_ip
from .verify import read_existing_server_config_value

# Common MySQL config file locations
MYSQL_CONF_PATHS = [
    Path("/etc/mysql/mysql.conf.d/mysqld.cnf"),  # Ubuntu/Debian
    Path("/etc/mysql/mariadb.conf.d/50-server.cnf"),  # MariaDB on Debian
    Path("/etc/my.cnf"),  # RHEL/Fedora
    Path("/etc/mysql/my.cnf"),  # Some Debian variants
]


def _get_debian_mysql_credentials() -> tuple[str, str] | None:
    """
    Get MySQL credentials from Debian maintenance file.

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
    """
    Start MySQL or MariaDB service.

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


def _find_mysql_admin_connection() -> tuple[list[str], dict[str, str]] | None:
    """
    Find a working MySQL admin connection method.

    Tries various methods to connect to MySQL as an admin user. The
    Debian-maintenance fallback uses a password from ``debian.cnf``.

    SECURITY: when a password is needed it is passed via ``MYSQL_PWD``
    env, never via ``-p{password}`` on argv. The latter would expose
    the maintenance password in /proc/<pid>/cmdline for any local user
    to read for the duration of every SQL execution. See
    notes/security.md §3.4.1.

    Returns:
        ``(argv, env_overrides)`` tuple — both must be threaded into
        every subsequent ``run_cmd`` call. ``None`` if no method works.
    """
    # Build list of (argv, env) candidates. argv is the prefix the
    # callers will append `-e <sql>` to; env carries any secrets that
    # must not appear in argv.
    candidates: list[tuple[list[str], dict[str, str]]] = [
        (["mysql"], {}),  # Socket auth as current user (root)
        (["sudo", "mysql"], {}),  # Socket auth via sudo
        (["mysql", "-u", "root"], {}),  # Traditional root
    ]

    # Also try Debian maintenance user if available — but route the
    # password through MYSQL_PWD instead of argv.
    debian_creds = _get_debian_mysql_credentials()
    if debian_creds:
        user, password = debian_creds
        candidates.insert(
            0,
            (["mysql", f"-u{user}"], {"MYSQL_PWD": password}),
        )

    for test_cmd, test_env in candidates:
        result = run_cmd(test_cmd + ["-e", "SELECT 1;"], check=False, env=test_env)
        if result.returncode == 0:
            print_detail(f"MySQL admin access via: {' '.join(test_cmd)}")
            return test_cmd, test_env

    return None


def _validate_mysql_password(password: str) -> bool:
    """
    Validate that password contains only safe characters for SQL.

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


def _create_mysql_hop3_user(
    root_cmd: list[str],
    root_env: dict[str, str],
    mysql_password: str,
) -> bool:
    """
    Create hop3 MySQL user with privileges.

    Args:
        root_cmd: Working MySQL admin command.
        root_env: Env overrides to apply to every admin invocation
            (carries MYSQL_PWD when the admin path needs a password).
        mysql_password: Password to set for hop3 user.

    Returns:
        True if user created successfully, False otherwise.
    """
    # SECURITY: the SQL below interpolates ``mysql_password`` directly into
    # CREATE/ALTER USER statements because MySQL admin tooling here is
    # invoked via ``mysql -e <sql>`` (no parameter binding available).
    # Safety relies on a two-step contract:
    #   1. The caller generates ``mysql_password`` via ``secrets.token_hex``
    #      in the installer flow — hex-charset only.
    #   2. We re-validate that contract here. If the generator ever changes,
    #      this gate must stay valid: validation is the only thing standing
    #      between callers and SQL injection.
    # Do not relax ``_validate_mysql_password`` without auditing every
    # f-string SQL query in this file.
    if not _validate_mysql_password(mysql_password):
        print_warning("Invalid characters in MySQL password")
        return False

    def run_sql(sql: str) -> subprocess.CompletedProcess:
        return run_cmd(root_cmd + ["-e", sql], check=False, env=root_env)

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
    """
    Verify hop3 user can connect to MySQL.

    SECURITY: pass the password via MYSQL_PWD instead of -p{password}.
    The latter exposes the secret in /proc/<pid>/cmdline for the
    duration of the verification (visible to other local users). Same
    fix shape as the addon-plugin's mysqldump/mysql calls; see
    notes/security.md §3.4.1.
    """
    result = run_cmd(
        [
            "mysql",
            "-u",
            "hop3",
            "-h",
            "127.0.0.1",
            "-e",
            "SELECT 1;",
        ],
        check=False,
        env={"MYSQL_PWD": mysql_password},
    )

    if result.returncode != 0:
        print_warning("MySQL user created but connection verification failed")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    return True


def _configure_mysql_bind_address(docker_ip: str) -> bool:
    """
    Configure MySQL to bind to Docker bridge address.

    Args:
        docker_ip: Docker bridge IP address.

    Returns:
        True if configuration was updated.
    """
    # Find MySQL config file
    mysql_conf = None
    for path in MYSQL_CONF_PATHS:
        if path.exists():
            mysql_conf = path
            break

    if not mysql_conf:
        print_warning("MySQL config file not found, skipping bind configuration")
        return False

    content = mysql_conf.read_text()

    # Check if already configured for Docker
    if docker_ip in content:
        print_detail(f"MySQL already configured for Docker bridge ({docker_ip})")
        return False

    # MySQL bind-address only accepts a single address, so we need to use 0.0.0.0
    # to listen on all interfaces, then rely on firewall/iptables for security
    # Alternatively, we can bind to a specific interface
    # For simplicity, we'll bind to 0.0.0.0 but this is controlled by user permissions
    new_bind = "bind-address = 0.0.0.0"

    if re.search(r"^#?\s*bind-address\s*=", content, re.MULTILINE):
        content = re.sub(
            r"^#?\s*bind-address\s*=.*$",
            new_bind,
            content,
            flags=re.MULTILINE,
        )
        print_detail("Updated MySQL bind-address to 0.0.0.0 (for Docker access)")
    else:
        # Add under [mysqld] section if it exists
        if "[mysqld]" in content:
            content = content.replace(
                "[mysqld]",
                f"[mysqld]\n{new_bind}",
            )
        else:
            content = f"[mysqld]\n{new_bind}\n{content}"
        print_detail("Added MySQL bind-address: 0.0.0.0 (for Docker access)")

    mysql_conf.write_text(content)
    return True


def _create_mysql_docker_user(
    root_cmd: list[str],
    root_env: dict[str, str],
    mysql_password: str,
    docker_ip: str,
) -> bool:
    """
    Create hop3 MySQL user for Docker network access.

    Args:
        root_cmd: Working MySQL admin command.
        root_env: Env overrides for every admin call (see
            ``_find_mysql_admin_connection`` for why this is separate
            from argv).
        mysql_password: Password for hop3 user.
        docker_ip: Docker bridge IP address.

    Returns:
        True if user created successfully, False otherwise.
    """
    if not _validate_mysql_password(mysql_password):
        return False

    def run_sql(sql: str) -> subprocess.CompletedProcess:
        return run_cmd(root_cmd + ["-e", sql], check=False, env=root_env)

    # Docker bridge network is typically 172.17.0.0/16
    # Extract network pattern (e.g., 172.17.%)
    parts = docker_ip.split(".")
    docker_network_pattern = f"{parts[0]}.{parts[1]}.%"

    # Drop existing Docker network user if exists
    run_sql(f"DROP USER IF EXISTS 'hop3'@'{docker_network_pattern}';")

    # Create hop3 user for Docker network
    result = run_sql(
        f"CREATE USER 'hop3'@'{docker_network_pattern}' "
        f"IDENTIFIED WITH mysql_native_password BY '{mysql_password}';"
    )
    if result.returncode != 0:
        print_warning(f"Failed to create MySQL user 'hop3'@'{docker_network_pattern}'")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    # Grant privileges
    result = run_sql(
        f"GRANT ALL PRIVILEGES ON *.* TO 'hop3'@'{docker_network_pattern}' "
        "WITH GRANT OPTION;"
    )
    if result.returncode != 0:
        print_warning(f"Failed to grant privileges to hop3@{docker_network_pattern}")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    run_sql("FLUSH PRIVILEGES;")
    print_detail(
        f"MySQL user 'hop3' configured for Docker network ({docker_network_pattern})"
    )
    return True


def _configure_mysql_for_docker(
    root_cmd: list[str],
    root_env: dict[str, str],
    mysql_password: str,
) -> None:
    """
    Configure MySQL for Docker container access.

    Args:
        root_cmd: Working MySQL admin command.
        root_env: Env overrides for every admin call.
        mysql_password: Password for hop3 user.
    """
    docker_ip = get_docker_bridge_ip()
    if not docker_ip:
        print_detail(
            "Docker bridge not found, MySQL will only accept local connections"
        )
        return

    # Configure bind address
    bind_changed = _configure_mysql_bind_address(docker_ip)

    # Create user for Docker network
    _create_mysql_docker_user(root_cmd, root_env, mysql_password, docker_ip)

    if bind_changed:
        # Restart MySQL to apply bind-address change
        result = run_cmd(["systemctl", "restart", "mysql"], check=False)
        if result.returncode != 0:
            run_cmd(["systemctl", "restart", "mariadb"], check=False)
        print_detail("MySQL configured to accept connections from Docker containers")


def setup_mysql(config: ServerInstallerConfig, distro: str) -> str | None:
    """
    Configure MySQL.

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
    admin = _find_mysql_admin_connection()

    if admin is None:
        print_warning("Could not connect to MySQL as admin")
        print_detail("Please check MySQL is running and has default authentication")
        print_detail("You may need to configure MySQL manually")
        return None
    mysql_root_cmd, mysql_root_env = admin

    # Reuse the password from a prior install if present — never rotate the
    # admin secret on redeploy (rotation desyncs the stored credential from the
    # MySQL user). Only a fresh install generates a new one.
    existing_pw = read_existing_server_config_value("MYSQL_SUPERUSER_PASSWORD")
    mysql_password = existing_pw or ("hop3_" + secrets.token_hex(16))

    # Create-or-update the hop3 user with privileges (idempotent: re-asserts the
    # same password on redeploy).
    if not _create_mysql_hop3_user(mysql_root_cmd, mysql_root_env, mysql_password):
        return None
    verb = "reused" if existing_pw else "created"
    print_success(f"MySQL user 'hop3' {verb} with privileges")

    # Configure for Docker container access
    _configure_mysql_for_docker(mysql_root_cmd, mysql_root_env, mysql_password)

    # Verify the connection works
    if not _verify_mysql_hop3_connection(mysql_password):
        return None

    print_success("MySQL connection verified successfully")
    return mysql_password
