# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL configuration."""

from __future__ import annotations

import re
import secrets
import time
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    has_systemd,
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)
from hop3_installer.constants import HOP3_USER

from .config import ServerInstallerConfig
from .verify import read_existing_server_config_value

# Common PostgreSQL config directories
POSTGRES_CONF_DIRS = [
    Path("/etc/postgresql"),  # Debian/Ubuntu (has version subdirs)
    Path("/var/lib/pgsql/data"),  # Fedora/RHEL
]


def _find_postgres_conf_dir() -> Path | None:
    """
    Find the PostgreSQL configuration directory.

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
    """
    Configure PostgreSQL to listen on all interfaces for Docker access.

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
    """
    Configure pg_hba.conf to allow connections from Docker networks.

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

    # Docker draws container networks from across RFC1918, not just 172.16/12:
    # docker0 is 172.17/16, but Compose projects routinely land in 192.168.x and
    # custom networks may use 10.x. Allow every RFC1918 block (md5, private-source
    # only). Kept in sync BY HAND with the runtime list in hop3-server's
    # postgresql plugin (``_ensure_pg_hba_docker_access``) — the installer is
    # stdlib-only and can't import the server package to share a constant.
    docker_networks = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]

    changed = False
    for net in docker_networks:
        rule = f"host    all    all    {net}    md5"
        if rule in content:
            continue
        if not changed:
            content += "\n# Allow Docker containers to connect (Hop3)\n"
            changed = True
        content += rule + "\n"

    if not changed:
        print_detail("pg_hba.conf already allows Docker networks")
        return False

    pg_hba.write_text(content)
    print_detail(f"Added pg_hba.conf entries for Docker networks: {docker_networks}")
    return True


_POSTGRES_PASSWORD_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _validate_postgres_password(password: str) -> bool:
    """
    Validate that the generated postgres password is shell/SQL-safe.

    SECURITY: the SQL-via-shell path below interpolates the password
    into ``ALTER USER … PASSWORD '…';`` which is then double-quoted and
    handed to ``psql -c "…"``. The password is generated by
    ``"hop3_" + secrets.token_hex(...)`` (or the hop3-app variant), so
    the alphabet is hex + ``_`` — but the validator pins the shape so
    a future regression in the generator can't sneak a quote or
    metacharacter through. Mirrors ``_validate_mysql_password``; see
    notes/security.md §3.1.2.
    """
    return bool(password) and bool(_POSTGRES_PASSWORD_RE.fullmatch(password))


def _set_hop3_postgres_password() -> str | None:
    """
    Set a password for the hop3 PostgreSQL user (for Docker connections).

    Returns:
        The generated password, or None if failed.
    """
    hop3_pg_password = "hop3app_" + secrets.token_hex(12)
    if not _validate_postgres_password(hop3_pg_password):
        print_warning("Generated postgres password failed shape check")
        return None

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
    """
    Configure PostgreSQL for Docker container access.

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
        _restart_postgres()
        print_detail(
            "PostgreSQL configured to accept connections from Docker containers"
        )

    return hop3_password


def _start_postgres_service(distro: str) -> bool:
    """
    Start PostgreSQL service.

    Uses systemd when available (bare-metal, VMs), falls back to
    ``pg_ctlcluster`` under supervisord (Docker test containers).

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

    if has_systemd():
        return _start_postgres_systemd()

    # Non-systemd: use pg_ctlcluster (Debian) or pg_ctl (Fedora)
    return _start_postgres_direct()


def _restart_postgres() -> None:
    """Restart PostgreSQL using the appropriate init system."""
    if has_systemd():
        run_cmd(["systemctl", "restart", "postgresql"], check=False)
    else:
        # Debian: pg_ctlcluster <version> main restart
        pg_versions = (
            sorted(Path("/etc/postgresql").iterdir(), reverse=True)
            if Path("/etc/postgresql").exists()
            else []
        )
        for version_dir in pg_versions:
            if (version_dir / "main").exists():
                run_cmd(
                    ["pg_ctlcluster", version_dir.name, "main", "restart"],
                    check=False,
                )
                return
        # Fedora fallback
        run_cmd(
            ["su", "-", "postgres", "-c", "pg_ctl restart -D /var/lib/pgsql/data"],
            check=False,
        )


def _start_postgres_systemd() -> bool:
    """Start PostgreSQL via systemd."""
    result = run_cmd(["systemctl", "enable", "postgresql"], check=False)
    if result.returncode != 0:
        print_warning("Failed to enable PostgreSQL service")

    result = run_cmd(["systemctl", "start", "postgresql"], check=False)
    if result.returncode != 0:
        print_warning("Could not start PostgreSQL via systemd")
        if result.stderr:
            print_detail(result.stderr[:200])
        return False

    return True


def _start_postgres_direct() -> bool:
    """
    Start PostgreSQL without systemd (containers, non-systemd hosts).

    On Debian/Ubuntu, ``pg_ctlcluster`` starts a specific cluster.
    On Fedora/RHEL, ``pg_ctl`` starts the data directory directly.
    """
    print_detail("systemd not available, starting PostgreSQL directly")

    # Debian/Ubuntu: pg_ctlcluster <version> <cluster> start
    pg_versions = (
        sorted(Path("/etc/postgresql").iterdir(), reverse=True)
        if Path("/etc/postgresql").exists()
        else []
    )
    for version_dir in pg_versions:
        cluster_dir = version_dir / "main"
        if cluster_dir.exists():
            version = version_dir.name
            print_detail(f"Starting PostgreSQL {version}/main via pg_ctlcluster")
            result = run_cmd(
                ["pg_ctlcluster", version, "main", "start"],
                check=False,
            )
            if result.returncode == 0:
                print_success(f"PostgreSQL {version} started")
                return True
            # Exit code 2 means already running
            if result.returncode == 2:
                print_detail(f"PostgreSQL {version} already running")
                return True
            print_warning(
                f"pg_ctlcluster {version} main start failed: "
                f"{result.stderr[:200] if result.stderr else 'no output'}"
            )

    # Fedora/RHEL fallback: pg_ctl
    data_dir = Path("/var/lib/pgsql/data")
    if data_dir.exists() and (data_dir / "postgresql.conf").exists():
        result = run_cmd(
            [
                "su",
                "-",
                "postgres",
                "-c",
                f"pg_ctl start -D {data_dir} -l /var/log/postgresql.log",
            ],
            check=False,
        )
        if result.returncode == 0:
            print_success("PostgreSQL started via pg_ctl")
            return True
        print_warning(
            f"pg_ctl start failed: {result.stderr[:200] if result.stderr else ''}"
        )

    print_warning("Could not start PostgreSQL: no cluster found")
    return False


def _create_postgres_role_and_db() -> bool:
    """
    Create hop3 PostgreSQL role and database.

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


# Verifying the superuser password can race a cluster that is still starting
# (supervisord/Docker), so re-assert + re-check a few times before giving up.
_SUPERUSER_VERIFY_ATTEMPTS = 5
_SUPERUSER_VERIFY_DELAY = 1.0


def _verify_superuser_tcp(password: str) -> bool:
    """
    Whether ``password`` authenticates the ``postgres`` role over TCP.

    This is the EXACT path hop3-server uses to provision addons (127.0.0.1:5432,
    password auth). A local peer ``ALTER`` can succeed — or hit a different
    cluster — while the TCP password is wrong; verifying here is what turns a
    silent credential desync into an install-time failure instead of every
    postgres app failing later with an opaque auth error.
    """
    argv = ["psql", "-h", "127.0.0.1", "-p", "5432", "-U", "postgres",
            "-d", "template1", "-tAc", "SELECT 1"]  # fmt: skip
    result = run_cmd(argv, check=False, env={"PGPASSWORD": password})
    return result.returncode == 0


def _set_postgres_password(existing: str | None = None) -> str | None:
    """
    (Re-)assert the postgres superuser password AND verify it over TCP.

    On redeploy ``existing`` is the password from a prior install: reuse it
    rather than rotating the superuser secret. Either way the password is
    re-asserted via ``ALTER USER`` — which reconciles a cluster that survived a
    ``rm -rf /home/hop3`` teardown — and then verified over the TCP path the
    server actually uses. Only a password that authenticates is returned; a
    value that can't be verified yields ``None`` so the install fails loud
    rather than shipping a hop3-server.toml the role won't honour.

    Returns:
        The verified password, or None if it could not be set and verified.
    """
    pg_password = existing or ("hop3_" + secrets.token_hex(16))
    if not _validate_postgres_password(pg_password):
        # An operator-customised password we can't safely interpolate into SQL:
        # we can't re-assert it, but it may already be correct on the role.
        if existing and _verify_superuser_tcp(existing):
            print_info("Reusing existing PostgreSQL superuser password")
            return existing
        print_warning("PostgreSQL superuser password failed shape check")
        return None

    sql_cmd = f"ALTER USER postgres PASSWORD '{pg_password}';"
    for attempt in range(_SUPERUSER_VERIFY_ATTEMPTS):
        run_cmd(["su", "-", "postgres", "-c", f'psql -c "{sql_cmd}"'], check=False)
        if _verify_superuser_tcp(pg_password):
            print_success(
                "PostgreSQL superuser password reused"
                if existing
                else "PostgreSQL superuser password configured"
            )
            return pg_password
        if attempt < _SUPERUSER_VERIFY_ATTEMPTS - 1:
            time.sleep(_SUPERUSER_VERIFY_DELAY)

    print_warning(
        "PostgreSQL superuser password could not be verified over TCP "
        "(127.0.0.1:5432 as 'postgres'). The role and hop3-server.toml would "
        "disagree, so addon provisioning would fail — refusing to ship it."
    )
    return None


def _verify_postgres_connection() -> bool:
    """
    Verify PostgreSQL connection works for hop3 user.

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
    """
    Configure PostgreSQL.

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

    # Set (or, on redeploy, reuse) the superuser password — never rotate it.
    existing_pw = read_existing_server_config_value("POSTGRES_SUPERUSER_PASSWORD")
    pg_password = _set_postgres_password(existing_pw)
    if pg_password is None:
        return None

    # Configure for Docker container access
    _configure_postgres_for_docker()

    # Verify connection
    if not _verify_postgres_connection():
        print_warning("PostgreSQL setup completed but verification failed")
        # Still return the password - the setup might be usable

    return pg_password
