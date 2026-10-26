# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Install and configure Garage, the object store behind the S3 addon.

Garage replaced MinIO in September 2026. The trigger was not licensing but
availability: MinIO withdrew its public server binaries, `dl.min.io` answers
410 for every path, and MinIO's GitHub releases carry no assets — so
``--with s3`` could not be installed at all. Garage is a single static musl
binary with no runtime dependencies, S3-compatible, AGPL, and built for the
self-hosted case. See ADR 060.

A single-node Garage needs three things beyond the binary: a config file
carrying two secrets, a running service, and a **cluster layout**. The layout
is the part that has no MinIO equivalent — until a node is given a role and
that role is committed, Garage accepts connections but serves no data.

Everything here is idempotent, and the secrets especially so: a redeploy must
never rotate them, or every key the addon has already handed to an app stops
working.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Generator
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    has_systemd,
    print_detail,
    print_info,
    print_success,
    process_manager_pending,
    run_cmd,
)

#: Pinned so an install is reproducible. Garage publishes static binaries per
#: target triple; both v1.0.1 and v1.1.0 were verified reachable.
GARAGE_VERSION = "v1.1.0"
GARAGE_BASE_URL = "https://garagehq.deuxfleurs.fr/_releases"

GARAGE_BIN = Path("/usr/local/bin/garage")
GARAGE_CONFIG_FILE = Path("/etc/garage.toml")
GARAGE_META_DIR = Path("/var/lib/garage/meta")
GARAGE_DATA_DIR = Path("/var/lib/garage/data")
GARAGE_SERVICE_FILE = Path("/etc/systemd/system/garage.service")
SUPERVISORD_CONF_FILE = Path("/etc/supervisor/conf.d/garage.conf")

HOP3_ENV_DIR = Path("/etc/hop3")
#: The bearer token the hop3-server S3 plugin authenticates to the admin API
#: with. Kept in its own file (0640 root:hop3) rather than in garage.toml,
#: which also holds the RPC secret and must not be group-readable.
GARAGE_ADMIN_TOKEN_FILE = HOP3_ENV_DIR / "garage-admin-token"

GARAGE_S3_PORT = 3900
GARAGE_RPC_PORT = 3901
GARAGE_ADMIN_PORT = 3903
GARAGE_ENDPOINT = f"http://127.0.0.1:{GARAGE_S3_PORT}"
GARAGE_ADMIN_ENDPOINT = f"http://127.0.0.1:{GARAGE_ADMIN_PORT}"

#: Garage's S3 region name. It must match what the backend signs with.
GARAGE_REGION = "garage"

#: The zone a single node is placed in. Garage models replication across
#: zones; with one node the name is arbitrary but must be set.
GARAGE_ZONE = "hop3"

#: How long to wait for the daemon to answer /health before giving up.
_HEALTH_TIMEOUT_S = 30.0
_HEALTH_POLL_S = 0.5


def _detect_target() -> str:
    """Garage's target triple for this machine."""
    machine = os.uname().machine.lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64-unknown-linux-musl"
    if machine in {"aarch64", "arm64"}:
        return "aarch64-unknown-linux-musl"
    msg = (
        f"No Garage binary is published for {machine!r}. Supported: x86_64, "
        f"aarch64. Install Garage manually and re-run, or run an external S3."
    )
    raise RuntimeError(msg)


def _install_binary() -> None:
    """Download the Garage binary unless the pinned version is already there."""
    if GARAGE_BIN.exists():
        result = run_cmd([str(GARAGE_BIN), "--version"], check=False)
        if GARAGE_VERSION.lstrip("v") in (result.stdout or ""):
            print_detail(f"Garage {GARAGE_VERSION} already installed")
            return
        print_detail(f"Replacing Garage at {GARAGE_BIN} with {GARAGE_VERSION}")

    target = _detect_target()
    url = f"{GARAGE_BASE_URL}/{GARAGE_VERSION}/{target}/garage"
    print_info(f"Downloading Garage {GARAGE_VERSION} ({target})...")
    GARAGE_BIN.parent.mkdir(parents=True, exist_ok=True)
    # Download beside the target and move into place, so an interrupted
    # download never leaves a truncated binary that looks installed.
    staged = GARAGE_BIN.with_suffix(".partial")
    run_cmd(["curl", "-fsSL", "-o", str(staged), url], check=True)
    staged.chmod(0o755)
    staged.replace(GARAGE_BIN)
    print_success(f"Garage installed at {GARAGE_BIN}")


def _existing_secret(key: str) -> str | None:
    """
    A secret already in garage.toml, so a redeploy reuses it.

    Rotating these would be silent breakage: `rpc_secret` identifies the node
    to itself across restarts, and `admin_token` is what every running
    hop3-server authenticates with. A redeploy that changed them would leave
    the addon unable to manage the buckets it created.
    """
    if not GARAGE_CONFIG_FILE.exists():
        return None
    try:
        content = GARAGE_CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else None


def _write_config() -> str:
    """Write /etc/garage.toml, preserving secrets. Returns the admin token."""
    # 32 bytes hex: rpc_secret is specified as a 32-byte hex string.
    rpc_secret = _existing_secret("rpc_secret") or secrets.token_hex(32)
    admin_token = _existing_secret("admin_token") or secrets.token_urlsafe(32)
    metrics_token = _existing_secret("metrics_token") or secrets.token_urlsafe(32)

    GARAGE_META_DIR.mkdir(parents=True, exist_ok=True)
    GARAGE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    config = f"""\
# Managed by hop3-install. Secrets are preserved across redeploys.
metadata_dir = "{GARAGE_META_DIR}"
data_dir = "{GARAGE_DATA_DIR}"
db_engine = "sqlite"

replication_factor = 1

rpc_bind_addr = "127.0.0.1:{GARAGE_RPC_PORT}"
rpc_public_addr = "127.0.0.1:{GARAGE_RPC_PORT}"
rpc_secret = "{rpc_secret}"

[s3_api]
s3_region = "{GARAGE_REGION}"
api_bind_addr = "127.0.0.1:{GARAGE_S3_PORT}"

[admin]
api_bind_addr = "127.0.0.1:{GARAGE_ADMIN_PORT}"
admin_token = "{admin_token}"
metrics_token = "{metrics_token}"
"""
    GARAGE_CONFIG_FILE.write_text(config)
    # 0600: this file holds the RPC secret. The admin token reaches the hop3
    # user through its own file, not by widening this one.
    GARAGE_CONFIG_FILE.chmod(0o600)
    print_detail(f"Wrote {GARAGE_CONFIG_FILE}")
    return admin_token


def _write_admin_token_file(admin_token: str) -> None:
    """
    Publish the admin token to the hop3 user, 0640 root:hop3.

    Group ownership may fail here on a fresh install (the hop3 group is
    created in a later step); :func:`fix_s3_env_ownership` fixes it up.
    """
    HOP3_ENV_DIR.mkdir(parents=True, exist_ok=True)
    GARAGE_ADMIN_TOKEN_FILE.write_text(f"{admin_token}\n")
    GARAGE_ADMIN_TOKEN_FILE.chmod(0o640)
    run_cmd(["chgrp", "hop3", str(GARAGE_ADMIN_TOKEN_FILE)], check=False)
    print_detail(f"Wrote {GARAGE_ADMIN_TOKEN_FILE} (admin token for hop3 user)")


def _has_supervisord() -> bool:
    """Return True if supervisord is available and writable conf.d exists."""
    return Path("/etc/supervisor/conf.d").is_dir()


def _write_systemd_unit() -> None:
    unit = f"""[Unit]
Description=Garage object storage for Hop3
Documentation=https://garagehq.deuxfleurs.fr/
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart={GARAGE_BIN} -c {GARAGE_CONFIG_FILE} server
Restart=always
RestartSec=5
LimitNOFILE=65536

# Security hardening
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
NoNewPrivileges=true
ReadWritePaths={GARAGE_META_DIR.parent}

[Install]
WantedBy=multi-user.target
"""
    GARAGE_SERVICE_FILE.write_text(unit)
    print_detail(f"Wrote {GARAGE_SERVICE_FILE}")


def _write_supervisord_unit() -> None:
    """Containers run supervisord rather than systemd."""
    conf = f"""[program:garage]
command={GARAGE_BIN} -c {GARAGE_CONFIG_FILE} server
autostart=true
autorestart=true
startretries=3
stderr_logfile=/var/log/garage.err.log
stdout_logfile=/var/log/garage.out.log
user=root
"""
    SUPERVISORD_CONF_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUPERVISORD_CONF_FILE.write_text(conf)
    print_detail(f"Wrote {SUPERVISORD_CONF_FILE} (supervisord fallback)")


def _start_service() -> None:
    """Start Garage under whichever process manager this host has."""
    # Init detection reads /proc/1/comm (has_systemd): the systemd *package*
    # can install systemctl on a container where systemd is not PID 1, and
    # `systemctl restart` there is fake success.
    if not has_systemd():
        # The deployer starts supervisord after this installer returns, and
        # it starts Garage from the program file written above. The conf.d
        # directory exists before supervisord runs, so it is no sign of one.
        if process_manager_pending():
            print_info("Garage will start when the process manager does")
            return
        run_cmd(["supervisorctl", "reread"])
        run_cmd(["supervisorctl", "update"])
        result = run_cmd(["supervisorctl", "start", "garage"], check=False)
        if result.returncode != 0 and "already started" not in (result.stdout or ""):
            raise CommandError(
                cmd=["supervisorctl", "start", "garage"],
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        return
    run_cmd(["systemctl", "daemon-reload"])
    run_cmd(["systemctl", "enable", "garage"])
    run_cmd(["systemctl", "restart", "garage"])


def _garage(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run the garage CLI against this node's config."""
    return run_cmd([str(GARAGE_BIN), "-c", str(GARAGE_CONFIG_FILE), *args], check=check)


def _layout_is_assigned() -> bool | None:
    """
    True/False if the node could be asked, None if it could not.

    The tri-state matters. An earlier version returned a plain bool from a
    substring test, so a `garage status` that failed for any reason — the node
    not running, most obviously — contained no "NO ROLE ASSIGNED" and was read
    as *already assigned*. The layout step then skipped itself, and the install
    finished with a Garage that answers health checks and stores nothing.
    """
    result = _garage("status")
    if result.returncode != 0:
        return None
    output = (result.stdout or "") + (result.stderr or "")
    return "NO ROLE ASSIGNED" not in output


def _capacity_gb() -> int:
    """
    Capacity to advertise, from the data filesystem's free space.

    Garage requires a capacity for any node holding data; it is a scheduling
    hint, not a quota. Nine tenths of what is free leaves the box room to
    breathe, with a floor so a small disk still yields a usable number.
    """
    free_bytes = shutil.disk_usage(GARAGE_DATA_DIR).free
    return max(1, int(free_bytes * 0.9) // (1000**3))


def _initialise_layout() -> None:
    """
    Give the single node a role and commit it. Raises if it cannot.

    Until this is done Garage runs, answers /health with 200, and fails every
    S3 request with "Could not reach quorum" — a server that looks installed
    and stores nothing. So this is not best-effort: a `--with` feature that
    cannot be made to work aborts the install rather than handing over a
    broken one.
    """
    assigned = _layout_is_assigned()
    if assigned:
        print_detail("Garage cluster layout already assigned")
        return
    if assigned is None:
        msg = (
            "Garage is not answering `garage status`, so its cluster layout "
            "could not be initialised. Without a layout, every S3 request "
            "fails with 'Could not reach quorum'."
        )
        raise RuntimeError(msg)

    result = _garage("node", "id", "-q")
    node_id = (result.stdout or "").strip().split("@")[0]
    if not node_id:
        msg = (
            f"Could not read the Garage node id (`garage node id -q` exited "
            f"{result.returncode}), so the cluster layout was not initialised."
        )
        raise RuntimeError(msg)

    capacity = _capacity_gb()
    assign = _garage(
        "layout", "assign", "-z", GARAGE_ZONE, "-c", f"{capacity}G", node_id
    )
    if assign.returncode != 0:
        msg = f"`garage layout assign` failed: {(assign.stderr or '')[:300]}"
        raise RuntimeError(msg)

    # Version 1 is the first committed layout on a fresh node.
    applied = _garage("layout", "apply", "--version", "1")
    if applied.returncode != 0:
        msg = f"`garage layout apply` failed: {(applied.stderr or '')[:300]}"
        raise RuntimeError(msg)

    # Verify rather than trust the exit code: a layout that was never
    # committed is the exact failure this guards against.
    if _layout_is_assigned() is not True:
        msg = (
            "`garage layout apply` reported success but the node still has "
            "no role assigned."
        )
        raise RuntimeError(msg)
    print_success(f"Garage cluster layout applied ({capacity} GB, zone {GARAGE_ZONE})")


@contextlib.contextmanager
def _garage_running() -> Generator[bool, None, None]:
    """
    Ensure a Garage node is up for the duration of the block.

    The layout is applied over RPC, so it needs a running node — and when the
    installer configures features there may be no process manager to ask. In a
    container the deployer starts supervisord only *after* the installer
    returns, so `supervisorctl start garage` fails and nothing is listening;
    the first version of this code warned and skipped the layout, which is how
    a server shipped that answered health checks and stored nothing.

    So the installer starts a node itself, does the one-off cluster setup, and
    stops it again. The layout lives in the metadata directory, so the node
    the process manager starts later inherits it.

    Yields True if a node is available (already running, or started here).
    """
    if _layout_is_assigned() is not None:
        yield True  # something already has one up
        return

    print_detail("Starting Garage briefly to initialise its cluster layout")
    process = subprocess.Popen(
        [str(GARAGE_BIN), "-c", str(GARAGE_CONFIG_FILE), "server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + _HEALTH_TIMEOUT_S
        while time.time() < deadline:
            if process.poll() is not None:
                yield False
                return
            if _layout_is_assigned() is not None:
                yield True
                return
            time.sleep(_HEALTH_POLL_S)
        yield False
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def fix_s3_env_ownership() -> None:
    """
    Set the admin-token file's group to ``hop3``.

    Called by the installer after the user/group creation step, because
    :func:`configure_s3` runs before the hop3 group exists. No-op when S3 was
    not enabled.
    """
    if not GARAGE_ADMIN_TOKEN_FILE.exists():
        return
    # hop3-server reads the token to create buckets: without the group, every
    # `hop3 addon create s3` is a permission error.
    run_cmd(["chgrp", "hop3", str(GARAGE_ADMIN_TOKEN_FILE)])
    GARAGE_ADMIN_TOKEN_FILE.chmod(0o640)
    print_detail(f"Set hop3 group ownership on {GARAGE_ADMIN_TOKEN_FILE}")


def configure_s3() -> None:
    """
    Install and configure Garage.

    Called from the installer's optional-packages step for ``--with s3``.
    """
    print_info(f"Configuring S3 (Garage {GARAGE_VERSION})...")

    _install_binary()
    admin_token = _write_config()
    _write_admin_token_file(admin_token)

    _write_systemd_unit()
    if _has_supervisord():
        _write_supervisord_unit()

    # The cluster layout is one-off, persistent state and must exist before
    # anything asks Garage to store an object. It is done against a node this
    # function is responsible for having up, rather than one a process manager
    # may or may not have started yet.
    with _garage_running() as running:
        if not running:
            msg = (
                f"Garage did not come up within {_HEALTH_TIMEOUT_S:g}s, so its "
                f"cluster layout could not be initialised. Check "
                f"`{GARAGE_BIN} -c {GARAGE_CONFIG_FILE} server` by hand."
            )
            raise RuntimeError(msg)
        _initialise_layout()

    # Hand over to the process manager for the long run. In a container this
    # is a no-op until the deployer starts supervisord, which is fine: the
    # layout is already committed to disk.
    _start_service()

    print_detail(
        f"Garage S3:    {GARAGE_ENDPOINT} "
        f"(use 'hop3 addon create s3 <name>' to provision buckets)"
    )
    print_detail(
        f"Garage admin: {GARAGE_ADMIN_ENDPOINT} (token in {GARAGE_ADMIN_TOKEN_FILE})"
    )
