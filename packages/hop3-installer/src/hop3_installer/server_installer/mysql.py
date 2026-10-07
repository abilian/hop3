# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""MySQL configuration."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    InstallStepError,
    control_service,
    print_detail,
    print_info,
    print_success,
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

    user = None
    password = None
    for raw in debian_cnf.read_text().split("\n"):
        line = raw.strip()
        if line.startswith("user"):
            user = line.split("=")[1].strip()
        elif line.startswith("password"):
            password = line.split("=")[1].strip()
        if user and password:
            return (user, password)
    return None


#: Service names to try, in order. Debian/Ubuntu ship `mysql`; MariaDB-based
#: distros ship `mariadb`.
_MYSQL_SERVICE_NAMES = ("mysql", "mariadb")


def _start_mysql_service() -> None:
    """
    Start MySQL or MariaDB, whichever this distro ships.

    Uses systemd when available, the init script otherwise — the same shape
    `_start_postgres_service` uses. There was no second branch: `systemctl start`
    was the only thing tried, so on a container it always failed and the install
    aborted with "Could not start MySQL service", two steps after PostgreSQL had
    started fine through its own non-systemd path in the same run.
    """
    control_service("start", *_MYSQL_SERVICE_NAMES)


def _restart_mysql() -> None:
    """Restart MySQL using whichever init system is actually running."""
    control_service("restart", *_MYSQL_SERVICE_NAMES)


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


def _run_admin_sql(
    root_cmd: list[str], root_env: dict[str, str], sql: str, what: str
) -> None:
    """
    Run one statement as the MySQL admin, or raise naming ``what`` it did.

    The statement goes on stdin, and the error names its purpose, never its
    text: several carry the hop3 password, which on argv (`mysql -e`) any
    local user read in /proc/<pid>/cmdline, and a CommandError prints its
    command.
    """
    result = run_cmd(root_cmd, check=False, env=root_env, stdin_text=sql)
    if result.returncode != 0:
        raise CommandError(
            cmd=["mysql", f"<{what}>"],
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )


def _check_mysql_password(mysql_password: str) -> None:
    """
    Refuse a password that is unsafe to interpolate into SQL.

    SECURITY: the statements below interpolate the password directly into
    CREATE USER, because the admin tooling here is ``mysql -e <sql>`` (no
    parameter binding). Generated passwords are hex; this re-validates that
    contract, which is the only thing standing between a stored password and
    SQL injection. Do not relax ``_validate_mysql_password`` without auditing
    every f-string SQL query in this file.
    """
    if not _validate_mysql_password(mysql_password):
        msg = (
            "the MySQL password in hop3-server.toml contains characters other "
            "than [A-Za-z0-9_-], so it cannot be set safely"
        )
        raise InstallStepError(msg)


def _create_mysql_hop3_user(
    root_cmd: list[str], root_env: dict[str, str], mysql_password: str
) -> None:
    """
    Create (or re-create) the hop3 MySQL user, with privileges.

    MySQL treats 'localhost' (socket) and '127.0.0.1' (TCP) as different
    hosts, so the user is created for both. mysql_native_password, for
    mysql-connector-python.
    """
    _check_mysql_password(mysql_password)
    for host in ("localhost", "127.0.0.1"):
        _run_admin_sql(root_cmd, root_env,
                       f"DROP USER IF EXISTS 'hop3'@'{host}';",
                       f"drop user hop3@{host}")  # fmt: skip
        _run_admin_sql(
            root_cmd,
            root_env,
            f"CREATE USER 'hop3'@'{host}' IDENTIFIED WITH mysql_native_password "
            f"BY '{mysql_password}';",
            f"create user hop3@{host}",
        )
        _run_admin_sql(
            root_cmd,
            root_env,
            f"GRANT ALL PRIVILEGES ON *.* TO 'hop3'@'{host}' WITH GRANT OPTION;",
            f"grant privileges to hop3@{host}",
        )
    _run_admin_sql(root_cmd, root_env, "FLUSH PRIVILEGES;", "flush privileges")


def _verify_mysql_hop3_connection(mysql_password: str) -> None:
    """
    Connect as hop3 over TCP, or raise with mysql's output.

    SECURITY: the password goes through MYSQL_PWD, never -p{password}, which
    would expose it in /proc/<pid>/cmdline; see notes/security.md §3.4.1.
    """
    run_cmd(
        ["mysql", "-u", "hop3", "-h", "127.0.0.1", "-e", "SELECT 1;"],
        env={"MYSQL_PWD": mysql_password},
    )


def _configure_mysql_bind_address(docker_ip: str) -> bool:
    """
    Make MySQL listen where Docker containers can reach it.

    MySQL's bind-address takes one address, so it listens on all interfaces
    and access is limited by the user host patterns.

    Returns:
        True if the configuration changed (a restart is needed).
    """
    mysql_conf = next((path for path in MYSQL_CONF_PATHS if path.exists()), None)
    if mysql_conf is None:
        paths = ", ".join(str(path) for path in MYSQL_CONF_PATHS)
        msg = f"no MySQL configuration file found ({paths}) to set bind-address in"
        raise InstallStepError(msg)

    content = mysql_conf.read_text()
    new_bind = "bind-address = 0.0.0.0"
    if new_bind in content:
        print_detail("MySQL already listens on all interfaces")
        return False

    if re.search(r"^#?\s*bind-address\s*=", content, re.MULTILINE):
        content = re.sub(
            r"^#?\s*bind-address\s*=.*$", new_bind, content, flags=re.MULTILINE
        )
    elif "[mysqld]" in content:
        content = content.replace("[mysqld]", f"[mysqld]\n{new_bind}")
    else:
        content = f"[mysqld]\n{new_bind}\n{content}"
    mysql_conf.write_text(content)
    print_detail("MySQL bind-address set to 0.0.0.0 (for Docker access)")
    return True


def _create_mysql_docker_user(
    root_cmd: list[str], root_env: dict[str, str], mysql_password: str, docker_ip: str
) -> None:
    """Create the hop3 MySQL user for the Docker bridge network (e.g. 172.17.%)."""
    _check_mysql_password(mysql_password)
    parts = docker_ip.split(".")
    pattern = f"{parts[0]}.{parts[1]}.%"
    _run_admin_sql(root_cmd, root_env,
                   f"DROP USER IF EXISTS 'hop3'@'{pattern}';",
                   f"drop user hop3@{pattern}")  # fmt: skip
    _run_admin_sql(
        root_cmd,
        root_env,
        f"CREATE USER 'hop3'@'{pattern}' IDENTIFIED WITH mysql_native_password "
        f"BY '{mysql_password}';",
        f"create user hop3@{pattern}",
    )
    _run_admin_sql(
        root_cmd,
        root_env,
        f"GRANT ALL PRIVILEGES ON *.* TO 'hop3'@'{pattern}' WITH GRANT OPTION;",
        f"grant privileges to hop3@{pattern}",
    )
    _run_admin_sql(root_cmd, root_env, "FLUSH PRIVILEGES;", "flush privileges")
    print_detail(f"MySQL user 'hop3' configured for Docker network ({pattern})")


def _configure_mysql_for_docker(
    root_cmd: list[str], root_env: dict[str, str], mysql_password: str
) -> None:
    """Let Docker containers reach MySQL, when the Docker bridge exists."""
    docker_ip = get_docker_bridge_ip()
    if not docker_ip:
        print_detail("No Docker bridge: MySQL accepts local connections only")
        return

    bind_changed = _configure_mysql_bind_address(docker_ip)
    _create_mysql_docker_user(root_cmd, root_env, mysql_password, docker_ip)
    if bind_changed:
        _restart_mysql()
    print_detail("MySQL configured to accept connections from Docker containers")


def setup_mysql(config: ServerInstallerConfig, distro: str) -> str | None:
    """
    Configure MySQL.

    Returns:
        The verified password of the hop3 MySQL user, or None when MySQL was
        not requested.

    Raises:
        CommandError, InstallStepError: a step failed.
    """
    if not config.with_mysql:
        return None

    print_info("Configuring MySQL...")
    _start_mysql_service()
    print_success("MySQL service started")

    admin = _find_mysql_admin_connection()
    if admin is None:
        msg = (
            "no admin connection to MySQL works (socket auth as root, sudo, "
            "root without a password, the Debian maintenance user)"
        )
        raise InstallStepError(msg)
    mysql_root_cmd, mysql_root_env = admin

    # Reuse the password from a prior install — never rotate it on redeploy:
    # rotation desyncs the stored credential from the MySQL user.
    existing_pw = read_existing_server_config_value("MYSQL_SUPERUSER_PASSWORD")
    mysql_password = existing_pw or ("hop3_" + secrets.token_hex(16))

    # Idempotent: re-asserts the same password on redeploy.
    _create_mysql_hop3_user(mysql_root_cmd, mysql_root_env, mysql_password)
    verb = "reused" if existing_pw else "created"
    print_success(f"MySQL user 'hop3' {verb} with privileges")

    _configure_mysql_for_docker(mysql_root_cmd, mysql_root_env, mysql_password)
    _verify_mysql_hop3_connection(mysql_password)
    print_success("MySQL connection verified successfully")
    return mysql_password
