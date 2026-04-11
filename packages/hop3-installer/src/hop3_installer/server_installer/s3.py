# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""S3-compatible object storage (MinIO) configuration.

Downloads MinIO server + the ``mc`` admin CLI, creates a systemd
service, and configures a ``hop3`` mc alias with generated admin
credentials.

**Licensing note:** MinIO moved toward a source-available tier in
2025. We'll replace this with Garage (https://garagehq.deuxfleurs.fr/,
genuinely AGPL) in a future release. The server-side plugin in
``hop3.plugins.s3`` already has a backend abstraction to make the
swap a one-liner on the plugin side; this installer will need its
own Garage variant.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from hop3_installer.common import (
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

# MinIO server binary (statically linked, ~70MB)
# We pin to a specific version for reproducibility. Bump deliberately.
MINIO_VERSION = "RELEASE.2024-11-07T00-52-20Z"
MINIO_BASE_URL = "https://dl.min.io/server/minio/release"

# mc admin CLI
MC_BASE_URL = "https://dl.min.io/client/mc/release"

# Installation paths
MINIO_BIN = Path("/usr/local/bin/minio")
MC_BIN = Path("/usr/local/bin/mc")
MINIO_DATA_DIR = Path("/var/lib/minio")
MINIO_CONFIG_DIR = Path("/etc/minio")
MINIO_CREDENTIALS_FILE = MINIO_CONFIG_DIR / "credentials.env"
MINIO_SERVICE_FILE = Path("/etc/systemd/system/minio.service")
SUPERVISORD_CONF_FILE = Path("/etc/supervisor/conf.d/minio.conf")

# MC_HOST_<alias> env file — readable by the hop3 user so the
# server plugin can drive the mc CLI without needing its own
# alias configuration.
HOP3_ENV_DIR = Path("/etc/hop3")
HOP3_S3_ENV_FILE = HOP3_ENV_DIR / "s3-env"

# Network
MINIO_API_PORT = 9000
MINIO_CONSOLE_PORT = 9001
MINIO_ENDPOINT = f"http://127.0.0.1:{MINIO_API_PORT}"


def _detect_arch() -> str:
    """Return the MinIO-style arch suffix for the current machine.

    MinIO provides linux-amd64, linux-arm64, linux-arm, linux-ppc64le,
    linux-s390x. We only need amd64 and arm64 in practice.
    """
    machine = os.uname().machine.lower()
    if machine in {"x86_64", "amd64"}:
        return "linux-amd64"
    if machine in {"aarch64", "arm64"}:
        return "linux-arm64"
    # Unknown arch — default to amd64 and hope binfmt handles it
    return "linux-amd64"


def _download(url: str, dest: Path) -> None:
    """Download a file to dest. Uses curl (must be available — it's a
    base dependency of the installer).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(
        [
            "curl",
            "-fsSL",
            "-o",
            str(dest),
            url,
        ],
        check=True,
    )
    dest.chmod(0o755)


def _install_minio_binary() -> None:
    """Download MinIO server binary if not already present."""
    if MINIO_BIN.exists():
        print_detail(f"MinIO already installed at {MINIO_BIN}")
        return

    arch = _detect_arch()
    url = f"{MINIO_BASE_URL}/{arch}/archive/minio.{MINIO_VERSION}"
    print_info(f"Downloading MinIO server ({arch}, {MINIO_VERSION})...")
    _download(url, MINIO_BIN)
    print_success(f"MinIO installed at {MINIO_BIN}")


def _install_mc_binary() -> None:
    """Download the mc admin CLI if not already present."""
    if MC_BIN.exists():
        print_detail(f"mc already installed at {MC_BIN}")
        return

    arch = _detect_arch()
    url = f"{MC_BASE_URL}/{arch}/mc"
    print_info(f"Downloading mc admin CLI ({arch})...")
    _download(url, MC_BIN)
    print_success(f"mc installed at {MC_BIN}")


def _generate_admin_credentials() -> tuple[str, str]:
    """Generate MinIO admin credentials, or reuse existing ones.

    Credentials are stored in MINIO_CREDENTIALS_FILE (0600) so the
    systemd unit and the hop3 server can both read them.
    """
    if MINIO_CREDENTIALS_FILE.exists():
        content = MINIO_CREDENTIALS_FILE.read_text()
        root_user = ""
        root_password = ""
        for line in content.splitlines():
            if line.startswith("MINIO_ROOT_USER="):
                root_user = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("MINIO_ROOT_PASSWORD="):
                root_password = line.split("=", 1)[1].strip().strip('"')
        if root_user and root_password:
            print_detail("Reusing existing MinIO admin credentials")
            return root_user, root_password

    print_detail("Generating new MinIO admin credentials")
    root_user = f"hop3admin{secrets.token_hex(4)}"
    root_password = secrets.token_urlsafe(32)

    MINIO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MINIO_CREDENTIALS_FILE.write_text(
        f'MINIO_ROOT_USER="{root_user}"\n'
        f'MINIO_ROOT_PASSWORD="{root_password}"\n'
        f'MINIO_VOLUMES="{MINIO_DATA_DIR}"\n'
        f'MINIO_OPTS="--address :{MINIO_API_PORT} '
        f'--console-address :{MINIO_CONSOLE_PORT}"\n'
    )
    MINIO_CREDENTIALS_FILE.chmod(0o600)
    return root_user, root_password


def _has_systemd() -> bool:
    """Return True if systemd is the init system.

    Containers (Docker test images) typically run supervisord instead.
    In that case we fall back to a supervisord config.
    """
    # systemctl is-system-running exits 0 only when systemd is PID 1.
    # Even on systems where the binary exists but systemd isn't
    # running, this returns non-zero (including "offline" and
    # "Failed to connect to bus").
    result = run_cmd(
        ["systemctl", "is-system-running", "--quiet"],
        check=False,
    )
    # is-system-running returns 0 for running, non-zero otherwise.
    # We also accept "degraded" (return code 1) and "starting" — any
    # state means systemd is alive.
    return result.returncode in {0, 1} and bool(result.stdout or result.stderr == "")


def _has_supervisord() -> bool:
    """Return True if supervisord is available and writable conf.d exists."""
    return Path("/etc/supervisor/conf.d").is_dir()


def _write_systemd_unit() -> None:
    """Write /etc/systemd/system/minio.service."""
    unit = f"""[Unit]
Description=MinIO object storage for Hop3
Documentation=https://min.io/docs
Wants=network-online.target
After=network-online.target

[Service]
Type=notify
EnvironmentFile={MINIO_CREDENTIALS_FILE}
ExecStart={MINIO_BIN} server $MINIO_OPTS $MINIO_VOLUMES
Restart=always
RestartSec=5
LimitNOFILE=65536

# Security hardening
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
NoNewPrivileges=true
ReadWritePaths={MINIO_DATA_DIR} {MINIO_CONFIG_DIR}

[Install]
WantedBy=multi-user.target
"""
    MINIO_SERVICE_FILE.write_text(unit)
    print_detail(f"Wrote {MINIO_SERVICE_FILE}")


def _write_supervisord_unit(root_user: str, root_password: str) -> None:
    """Write /etc/supervisor/conf.d/minio.conf as a systemd fallback.

    Containers use supervisord instead of systemd. This writes a
    program block that runs MinIO with the same args and env as the
    systemd unit. Supervisord doesn't understand the notify protocol,
    so we use Type=simple equivalent.
    """
    # Supervisord doesn't have EnvironmentFile; pass env vars inline.
    env_line = (
        f'MINIO_ROOT_USER="{root_user}",'
        f'MINIO_ROOT_PASSWORD="{root_password}"'
    )
    conf = f"""[program:minio]
command={MINIO_BIN} server --address :{MINIO_API_PORT} --console-address :{MINIO_CONSOLE_PORT} {MINIO_DATA_DIR}
environment={env_line}
autostart=true
autorestart=true
startretries=3
stderr_logfile=/var/log/minio.err.log
stdout_logfile=/var/log/minio.out.log
user=root
"""
    SUPERVISORD_CONF_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUPERVISORD_CONF_FILE.write_text(conf)
    print_detail(f"Wrote {SUPERVISORD_CONF_FILE} (supervisord fallback)")


def _setup_data_dir() -> None:
    """Create the MinIO data directory."""
    MINIO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    # MinIO runs as root for now (simplifies the systemd unit). A
    # dedicated minio user is a nice-to-have for later.
    print_detail(f"Data directory: {MINIO_DATA_DIR}")


def _start_minio_service_systemd() -> bool:
    """Start MinIO via systemd. Return True on success."""
    run_cmd(["systemctl", "daemon-reload"], check=False)
    run_cmd(["systemctl", "enable", "minio"], check=False)
    result = run_cmd(["systemctl", "restart", "minio"], check=False)
    if result.returncode != 0:
        print_warning(f"systemctl restart minio failed: {result.stderr[:200]}")
        return False
    return True


def _start_minio_service_supervisord() -> bool:
    """Start MinIO via supervisord. Return True on success."""
    run_cmd(["supervisorctl", "reread"], check=False)
    run_cmd(["supervisorctl", "update"], check=False)
    result = run_cmd(["supervisorctl", "start", "minio"], check=False)
    # supervisorctl start returns 0 even when the program was already
    # running (prints "minio: ERROR (already started)"). Accept both
    # exit-0 and the already-started sentinel.
    if result.returncode != 0 and "already started" not in result.stdout:
        print_warning(f"supervisorctl start minio failed: {result.stderr[:200]}")
        return False
    return True


def _start_minio_service() -> None:
    """Start MinIO via systemd or supervisord, then verify it's alive.

    Picks the init system automatically: systemd if it's PID 1
    (bare-metal, VMs), supervisord otherwise (Docker test containers).
    """
    import time  # noqa: PLC0415

    started = False
    if _has_systemd():
        started = _start_minio_service_systemd()
    elif _has_supervisord():
        print_detail("systemd not available, using supervisord fallback")
        started = _start_minio_service_supervisord()
    else:
        print_warning(
            "Neither systemd nor supervisord found — MinIO will not be "
            "started automatically. Start it manually with: "
            f"{MINIO_BIN} server {MINIO_DATA_DIR}"
        )
        return

    if not started:
        return

    # Wait briefly for MinIO to listen on its port
    for _ in range(15):
        probe = run_cmd(
            ["curl", "-sSf", "-o", "/dev/null", f"{MINIO_ENDPOINT}/minio/health/live"],
            check=False,
        )
        if probe.returncode == 0:
            print_success("MinIO is running and healthy")
            return
        time.sleep(1)

    print_warning(
        "MinIO started but did not respond to health check within 15s. "
        f"Check logs and 'curl {MINIO_ENDPOINT}/minio/health/live'."
    )


def _configure_mc_alias(root_user: str, root_password: str) -> None:
    """Register the 'hop3' mc alias pointing at the local MinIO.

    This is the alias the hop3-server plugin uses to manage buckets
    and access keys.
    """
    result = run_cmd(
        [
            "mc",
            "alias",
            "set",
            "hop3",
            MINIO_ENDPOINT,
            root_user,
            root_password,
        ],
        check=False,
    )
    if result.returncode == 0:
        print_success("mc alias 'hop3' configured")
    else:
        print_warning(f"Failed to set mc alias: {result.stderr[:200]}")


def _write_hop3_env_file(root_user: str, root_password: str) -> None:
    """Write ``/etc/hop3/s3-env`` with ``MC_HOST_hop3=...``.

    MinIO's ``mc`` CLI reads ``MC_HOST_<alias>`` env vars and uses
    them as an ad-hoc alias, bypassing ``~/.mc/config.json``. This
    lets the hop3 user drive ``mc`` without having an alias config
    in its own home directory.

    The file is 0640 initially owned by root:root. Group ownership
    is fixed up later by :func:`fix_s3_env_ownership` after the
    hop3 user has been created (in step 2 of the installer).
    """
    HOP3_ENV_DIR.mkdir(parents=True, exist_ok=True)
    host = MINIO_ENDPOINT.replace("http://", "")
    # MC_HOST URL format: http://ACCESS:SECRET@host:port
    host_url = f"http://{root_user}:{root_password}@{host}"
    HOP3_S3_ENV_FILE.write_text(f"MC_HOST_hop3={host_url}\n")
    # 0640: root can read/write, hop3 group can read, others blocked.
    HOP3_S3_ENV_FILE.chmod(0o640)
    # Try to set group ownership now — this only works if the hop3
    # group already exists (re-install case). On fresh installs the
    # user/group is created in step 2; fix_s3_env_ownership() runs
    # after that step to fix things up.
    run_cmd(["chgrp", "hop3", str(HOP3_S3_ENV_FILE)], check=False)
    print_detail(f"Wrote {HOP3_S3_ENV_FILE} (MC_HOST_hop3 for hop3 user)")


def fix_s3_env_ownership() -> None:
    """Set ``/etc/hop3/s3-env`` group ownership to ``hop3``.

    Called by the main installer flow after step 2 (user/group
    creation) to fix up the file that ``configure_s3`` wrote in
    step 1 (when the hop3 group didn't yet exist).

    No-op if the file doesn't exist (S3 wasn't enabled).
    """
    if not HOP3_S3_ENV_FILE.exists():
        return
    result = run_cmd(["chgrp", "hop3", str(HOP3_S3_ENV_FILE)], check=False)
    if result.returncode == 0:
        # Also re-assert the mode in case something interfered.
        HOP3_S3_ENV_FILE.chmod(0o640)
        print_detail(f"Set hop3 group ownership on {HOP3_S3_ENV_FILE}")
    else:
        print_warning(
            f"Could not set hop3 group on {HOP3_S3_ENV_FILE}: "
            f"{result.stderr[:200]}"
        )


def configure_s3() -> None:
    """Install and configure MinIO for Hop3 use.

    Called from the installer's optional-packages step when
    ``--with s3`` is passed.
    """
    print_info("Configuring S3 (MinIO)...")

    _install_minio_binary()
    _install_mc_binary()
    _setup_data_dir()
    root_user, root_password = _generate_admin_credentials()

    # Write both unit files — the right one will be used depending
    # on what init system is actually present. This is harmless: an
    # unused systemd unit file just sits there until the system is
    # re-provisioned.
    _write_systemd_unit()
    if _has_supervisord():
        _write_supervisord_unit(root_user, root_password)

    # Write the env file BEFORE starting the service so the hop3 user
    # can use mc against MinIO as soon as it's up.
    _write_hop3_env_file(root_user, root_password)

    _start_minio_service()
    _configure_mc_alias(root_user, root_password)

    print_detail(
        "MinIO API:     http://127.0.0.1:9000 "
        "(use 'hop3 addons:create s3 <name>' to provision buckets)"
    )
    print_detail(
        "MinIO Console: http://127.0.0.1:9001 "
        f"(root user in {MINIO_CREDENTIALS_FILE})"
    )
