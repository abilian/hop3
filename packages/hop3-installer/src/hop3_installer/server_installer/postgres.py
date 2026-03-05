# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL configuration."""

from __future__ import annotations

import re
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

# Common PostgreSQL config directories
POSTGRES_CONF_DIRS = [
    Path("/etc/postgresql"),  # Debian/Ubuntu (has version subdirs)
    Path("/var/lib/pgsql/data"),  # Fedora/RHEL
]


def _get_docker_bridge_ip() -> str | None:
    """Get the Docker bridge network IP (usually 172.17.0.1).

    Returns:
        Docker bridge IP if available, None otherwise.
    """
    result = run_cmd(
        ["ip", "addr", "show", "docker0"],
        check=False,
    )
    if result.returncode != 0:
        return None

    # Parse output for inet address: "inet 172.17.0.1/16 ..."
    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", result.stdout)
    if match:
        return match.group(1)
    return None


def _find_postgres_conf_dir() -> Path | None:
    """Find the PostgreSQL configuration directory.

    Returns:
        Path to config directory, or None if not found.
    """
    for base_dir in POSTGRES_CONF_DIRS:
        if not base_dir.exists():
            continue

        # Debian/Ubuntu: /etc/postgresql/<version>/main/
        if base_dir == Path("/etc/postgresql"):
            # Find the latest version directory
            version_dirs = sorted(base_dir.iterdir(), reverse=True)
            for version_dir in version_dirs:
                conf_dir = version_dir / "main"
                if conf_dir.exists() and (conf_dir / "postgresql.conf").exists():
                    return conf_dir

        # Fedora/RHEL: /var/lib/pgsql/data/
        elif (base_dir / "postgresql.conf").exists():
            return base_dir

    return None


def _configure_postgres_listen_addresses(_unused: str = "") -> bool:
    """Configure PostgreSQL to listen on all interfaces for Docker access.

    Docker Compose creates its own bridge networks with different gateway IPs,
    so we need PostgreSQL to listen on all interfaces. Access is controlled
    by pg_hba.conf which restricts connections to Docker network ranges.

    Returns:
        True if configuration was updated.
    """
    conf_dir = _find_postgres_conf_dir()
    if not conf_dir:
        print_warning("PostgreSQL config directory not found")
        return False

    postgresql_conf = conf_dir / "postgresql.conf"
    if not postgresql_conf.exists():
        print_warning(f"postgresql.conf not found at {postgresql_conf}")
        return False

    content = postgresql_conf.read_text()

    # Check if already configured to listen on all interfaces
    if "listen_addresses = '*'" in content:
        print_detail("PostgreSQL already configured to listen on all interfaces")
        return False

    # Listen on all interfaces - access is controlled by pg_hba.conf
    # This is needed because docker-compose networks have varying gateway IPs
    new_listen = "listen_addresses = '*'"

    if re.search(r"^#?\s*listen_addresses\s*=", content, re.MULTILINE):
        content = re.sub(
            r"^#?\s*listen_addresses\s*=\s*'[^']*'",
            new_listen,
            content,
            flags=re.MULTILINE,
        )
        print_detail(f"Updated PostgreSQL listen_addresses: {new_listen}")
    else:
        # Add at the beginning if not present
        content = f"{new_listen}\n{content}"
        print_detail(f"Added PostgreSQL listen_addresses: {new_listen}")

    postgresql_conf.write_text(content)
    return True


def _configure_postgres_hba(_unused: str = "") -> bool:
    """Configure pg_hba.conf to allow connections from Docker networks.

    Returns:
        True if configuration was updated.
    """
    conf_dir = _find_postgres_conf_dir()
    if not conf_dir:
        return False

    pg_hba = conf_dir / "pg_hba.conf"
    if not pg_hba.exists():
        print_warning(f"pg_hba.conf not found at {pg_hba}")
        return False

    content = pg_hba.read_text()

    # Use 172.16.0.0/12 to cover all typical Docker networks:
    # - docker0 bridge: 172.17.0.0/16
    # - docker-compose networks: 172.18.0.0/16, 172.19.0.0/16, etc.
    # The /12 range covers 172.16.0.0 - 172.31.255.255
    docker_network = "172.16.0.0/12"

    # Check if already configured
    if docker_network in content:
        print_detail(
            f"pg_hba.conf already configured for Docker networks ({docker_network})"
        )
        return False

    # Add host entry for Docker networks
    # Allow md5 authentication for ALL users from Docker containers
    # (app addons create specific users like myapp_postgres_user)
    hba_entry = f"\n# Allow Docker containers to connect (Hop3)\nhost    all    all    {docker_network}    md5\n"

    content += hba_entry
    pg_hba.write_text(content)
    print_detail(f"Added pg_hba.conf entry for Docker networks: {docker_network}")
    return True


def _set_hop3_postgres_password() -> str | None:
    """Set a password for the hop3 PostgreSQL user (for Docker connections).

    Returns:
        The generated password, or None if failed.
    """
    hop3_pg_password = "hop3app_" + secrets.token_hex(12)

    sql_cmd = f"ALTER USER {HOP3_USER} PASSWORD '{hop3_pg_password}';"
    result = run_cmd(
        ["su", "-", "postgres", "-c", f'psql -c "{sql_cmd}"'],
        check=False,
    )

    if result.returncode != 0:
        print_warning("Could not set hop3 PostgreSQL user password")
        if result.stderr:
            print_detail(result.stderr[:200])
        return None

    print_detail("hop3 PostgreSQL user password configured for Docker access")
    return hop3_pg_password


def _configure_postgres_for_docker() -> str | None:
    """Configure PostgreSQL for Docker container access.

    Always configures PostgreSQL for Docker networks since Hop3 supports
    Docker deployments. The docker0 bridge may not exist yet if Docker
    isn't running, but docker-compose networks will be created later.

    Returns:
        The hop3 user password if configured, None otherwise.
    """
    # Check if Docker is installed (not necessarily running)
    docker_installed = (
        Path("/usr/bin/docker").exists() or Path("/usr/local/bin/docker").exists()
    )
    if not docker_installed:
        print_detail("Docker not installed, skipping PostgreSQL Docker configuration")
        return None

    # Configure listen_addresses (always, for future Docker usage)
    listen_changed = _configure_postgres_listen_addresses("docker")

    # Configure pg_hba.conf (always, for future Docker usage)
    hba_changed = _configure_postgres_hba("docker")

    # Set password for hop3 user (needed for md5 auth from Docker)
    hop3_password = None
    if listen_changed or hba_changed:
        hop3_password = _set_hop3_postgres_password()

    if listen_changed or hba_changed:
        # Restart PostgreSQL to apply changes
        run_cmd(["systemctl", "restart", "postgresql"], check=False)
        print_detail(
            "PostgreSQL configured to accept connections from Docker containers"
        )

    return hop3_password


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

    # Configure for Docker container access
    _configure_postgres_for_docker()

    # Verify connection
    if not _verify_postgres_connection():
        print_warning("PostgreSQL setup completed but verification failed")
        # Still return the password - the setup might be usable

    return pg_password
