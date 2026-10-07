# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL configuration."""

from __future__ import annotations

import re
import secrets
import subprocess
import time
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    InstallStepError,
    has_systemd,
    print_detail,
    print_info,
    print_success,
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


def _postgres_conf_dir() -> Path:
    """The running cluster's config directory, which must exist by now."""
    conf_dir = _find_postgres_conf_dir()
    if conf_dir is None:
        dirs = ", ".join(str(d) for d in POSTGRES_CONF_DIRS)
        msg = f"no PostgreSQL configuration found under {dirs}"
        raise InstallStepError(msg)
    return conf_dir


def _configure_postgres_listen_addresses(_unused: str = "") -> bool:
    """
    Configure PostgreSQL to listen on all interfaces for Docker access.

    Docker Compose creates its own bridge networks with different gateway IPs,
    so we need PostgreSQL to listen on all interfaces. Access is controlled
    by pg_hba.conf which restricts connections to Docker network ranges.

    Returns:
        True if configuration was updated.
    """
    postgresql_conf = _postgres_conf_dir() / "postgresql.conf"
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
    pg_hba = _postgres_conf_dir() / "pg_hba.conf"
    if not pg_hba.exists():
        msg = f"{pg_hba} not found: the PostgreSQL cluster is incomplete"
        raise InstallStepError(msg)

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


def _configure_postgres_for_docker() -> None:
    """
    Let Docker containers reach PostgreSQL, when Docker is installed.

    Listen on every interface, with pg_hba.conf admitting only the RFC1918
    ranges Docker draws its networks from (password auth). The docker0 bridge
    may not exist yet; Compose networks are created later.
    """
    docker_installed = (
        Path("/usr/bin/docker").exists() or Path("/usr/local/bin/docker").exists()
    )
    if not docker_installed:
        print_detail("Docker not installed, skipping PostgreSQL Docker configuration")
        return

    listen_changed = _configure_postgres_listen_addresses("docker")
    hba_changed = _configure_postgres_hba("docker")
    if listen_changed or hba_changed:
        _restart_postgres()
        print_detail(
            "PostgreSQL configured to accept connections from Docker containers"
        )


def _start_postgres_service(distro: str) -> None:
    """
    Start PostgreSQL, or raise with the reason.

    Uses systemd when available (bare-metal, VMs), and ``pg_ctlcluster`` or
    ``pg_ctl`` under supervisord (Docker test containers).
    """
    # Fedora's cluster must be initialised before its first start.
    if distro == "fedora" and not Path("/var/lib/pgsql/data/pg_hba.conf").exists():
        run_cmd(["postgresql-setup", "--initdb"])

    if has_systemd():
        run_cmd(["systemctl", "enable", "postgresql"])
        run_cmd(["systemctl", "start", "postgresql"])
        return
    _start_postgres_direct()


def _restart_postgres() -> None:
    """Restart PostgreSQL using the appropriate init system."""
    if has_systemd():
        run_cmd(["systemctl", "restart", "postgresql"])
        return
    version = _debian_cluster_version()
    if version:
        run_cmd(["pg_ctlcluster", version, "main", "restart"])
        return
    run_cmd(["su", "-", "postgres", "-c", "pg_ctl restart -D /var/lib/pgsql/data"])


def _debian_cluster_version() -> str | None:
    """The newest Debian cluster's version (``/etc/postgresql/<v>/main``)."""
    root = Path("/etc/postgresql")
    if not root.exists():
        return None
    versions = sorted(
        (d.name for d in root.iterdir() if (d / "main").exists()), reverse=True
    )
    return versions[0] if versions else None


def _start_postgres_direct() -> None:
    """
    Start PostgreSQL without systemd (containers, non-systemd hosts).

    On Debian/Ubuntu, ``pg_ctlcluster`` starts the newest cluster; on
    Fedora/RHEL, ``pg_ctl`` starts the data directory. A cluster that fails to
    start raises: falling back to an older one started the wrong version and
    reported success.
    """
    print_detail("systemd not available, starting PostgreSQL directly")

    version = _debian_cluster_version()
    if version:
        print_detail(f"Starting PostgreSQL {version}/main via pg_ctlcluster")
        result = run_cmd(["pg_ctlcluster", version, "main", "start"], check=False)
        # Exit code 2 means already running.
        if result.returncode not in {0, 2}:
            raise CommandError(
                cmd=["pg_ctlcluster", version, "main", "start"],
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        return

    data_dir = Path("/var/lib/pgsql/data")
    if (data_dir / "postgresql.conf").exists():
        run_cmd(["su", "-", "postgres", "-c",
                 f"pg_ctl start -D {data_dir} -l /var/log/postgresql.log"])  # fmt: skip
        return

    msg = "no PostgreSQL cluster found (/etc/postgresql/<version>/main, /var/lib/pgsql/data)"
    raise InstallStepError(msg)


def _create_postgres_role_and_db() -> None:
    """
    Create the hop3 PostgreSQL role and database; existing ones are kept.

    A failure used to be printed as a detail line and followed by a success
    line, so the install went on without the role every app is created by.
    """
    for command in (
        f"createuser --createdb {HOP3_USER}",
        f"createdb -O {HOP3_USER} hop3",
    ):
        result = run_cmd(["su", "-", "postgres", "-c", command], check=False)
        if result.returncode != 0 and "already exists" not in (result.stderr or ""):
            raise CommandError(
                cmd=["su", "-", "postgres", "-c", command],
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
    print_success("PostgreSQL role and database created")


# Verifying the superuser password can race a cluster that is still starting
# (supervisord/Docker), so re-assert + re-check a few times before giving up.
_SUPERUSER_VERIFY_ATTEMPTS = 5
_SUPERUSER_VERIFY_DELAY = 1.0


def _verify_superuser_tcp(password: str) -> subprocess.CompletedProcess:
    """
    Try ``password`` on the ``postgres`` role over TCP; returncode 0 if it works.

    This is the EXACT path hop3-server uses to provision addons (127.0.0.1:5432,
    password auth). A local peer ``ALTER`` can succeed — or hit a different
    cluster — while the TCP password is wrong; verifying here is what turns a
    silent credential desync into an install-time failure instead of every
    postgres app failing later with an opaque auth error.
    """
    argv = ["psql", "-h", "127.0.0.1", "-p", "5432", "-U", "postgres",
            "-d", "template1", "-tAc", "SELECT 1"]  # fmt: skip
    return run_cmd(argv, check=False, env={"PGPASSWORD": password})


def _set_postgres_password(existing: str | None = None) -> str:
    """
    (Re-)assert the postgres superuser password AND verify it over TCP.

    On redeploy ``existing`` is the password from a prior install: reuse it
    rather than rotating the superuser secret. Either way the password is
    re-asserted via ``ALTER USER`` — which reconciles a cluster that survived a
    ``rm -rf /home/hop3`` teardown — and then verified over the TCP path the
    server actually uses. Only a password that authenticates is returned; a
    value that can't be verified raises, rather than shipping a
    hop3-server.toml the role won't honour.

    Returns:
        The verified password.

    Raises:
        InstallStepError: it could not be set and verified.
    """
    pg_password = existing or ("hop3_" + secrets.token_hex(16))
    if not _validate_postgres_password(pg_password):
        # An operator-customised password we can't safely interpolate into SQL:
        # we can't re-assert it, but it may already be correct on the role.
        if existing and _verify_superuser_tcp(existing).returncode == 0:
            print_info("Reusing existing PostgreSQL superuser password")
            return existing
        msg = (
            "the PostgreSQL superuser password in hop3-server.toml is not "
            "[A-Za-z0-9_]+ and does not authenticate either, so it can be "
            "neither re-asserted nor kept"
        )
        raise InstallStepError(msg)

    # On stdin: on argv the password was readable by any local user in
    # /proc/<pid>/cmdline while psql ran.
    sql = f"ALTER USER postgres PASSWORD '{pg_password}';"
    attempts = 0
    while True:
        altered = run_cmd(
            ["su", "-", "postgres", "-c", "psql -v ON_ERROR_STOP=1"],
            check=False,
            stdin_text=sql,
        )
        verified = _verify_superuser_tcp(pg_password)
        if verified.returncode == 0:
            print_success(
                "PostgreSQL superuser password reused"
                if existing
                else "PostgreSQL superuser password configured"
            )
            return pg_password
        attempts += 1
        if attempts == _SUPERUSER_VERIFY_ATTEMPTS:
            break
        time.sleep(_SUPERUSER_VERIFY_DELAY)

    # Which of the two failed is the diagnosis: refused, wrong password, or
    # an ALTER that never ran.
    msg = (
        "the PostgreSQL superuser password could not be verified over TCP "
        "(127.0.0.1:5432 as 'postgres'): the role and hop3-server.toml would "
        "disagree, and every PostgreSQL addon would fail to provision. "
        f"ALTER USER (exit {altered.returncode}): "
        f"{(altered.stderr or altered.stdout or '').strip()[:300]}; "
        f"TCP check (exit {verified.returncode}): "
        f"{(verified.stderr or verified.stdout or '').strip()[:300]}"
    )
    raise InstallStepError(msg)


def _verify_postgres_connection() -> None:
    """Connect as hop3 by peer authentication, or raise with psql's output."""
    run_cmd(["su", "-", HOP3_USER, "-c", "psql -d hop3 -c 'SELECT 1;'"])
    print_success("PostgreSQL connection verified")


def setup_postgres(config: ServerInstallerConfig, distro: str) -> str | None:
    """
    Configure PostgreSQL.

    Returns:
        The verified postgres superuser password, or None when skipped.

    Raises:
        CommandError, InstallStepError: a step failed.
    """
    if config.skip_postgres:
        print_info("Skipping PostgreSQL setup (--skip-postgres)")
        return None

    print_info("Configuring PostgreSQL...")
    _start_postgres_service(distro)
    print_success("PostgreSQL service started")
    _create_postgres_role_and_db()

    # Set (or, on redeploy, reuse) the superuser password — never rotate it.
    existing_pw = read_existing_server_config_value("POSTGRES_SUPERUSER_PASSWORD")
    pg_password = _set_postgres_password(existing_pw)

    _configure_postgres_for_docker()
    _verify_postgres_connection()
    return pg_password
