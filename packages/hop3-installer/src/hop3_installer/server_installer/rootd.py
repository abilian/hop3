# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: SIM105

"""hop3-rootd installation and migration.

Installs the privileged-operations daemon: systemd `.service` and
`.socket` units, logrotate config, runtime/state/log directories, an
empty state.json, the `inet hop3` nftables table, and enables the unit.

Also handles the upgrade-time migration: when an existing installation
has /etc/sudoers.d/hop3 (the four nginx NOPASSWD entries), the fragment
is removed AFTER hop3-rootd is up — the point of no return per ADR 041
§12.

See ADR 041 §14 (Distribution and install) and §12 (Sudoers fragment
retirement).
"""

from __future__ import annotations

from pathlib import Path

from hop3_installer.common import (
    CommandError,
    cmd_exists,
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)

# --- Paths and content ---------------------------------------------------

SERVICE_PATH = Path("/etc/systemd/system/hop3-rootd.service")
SOCKET_PATH = Path("/etc/systemd/system/hop3-rootd.socket")
LOGROTATE_PATH = Path("/etc/logrotate.d/hop3-rootd")
SUDOERS_FRAGMENT = Path("/etc/sudoers.d/hop3")
STATE_DIR = Path("/var/lib/hop3-rootd")
STATE_FILE = STATE_DIR / "state.json"
LOG_DIR = Path("/var/log/hop3-rootd")
RUNTIME_DIR = Path("/run/hop3-rootd")


# Paths to the daemon entry script. Two candidates depending on install
# style: editable install via `uv sync` (script lives in the venv's bin
# dir) or production install (TBD — for now we shell out to the venv).
def _resolve_daemon_command() -> str:
    """Find the hop3-rootd executable. Returns an absolute path or raises."""
    # Common installation locations to probe in order.
    candidates = [
        Path("/usr/local/bin/hop3-rootd"),
        Path("/opt/hop3/.venv/bin/hop3-rootd"),  # production venv
        Path("/home/hop3/.venv/bin/hop3-rootd"),  # legacy
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return str(c)
    # Fallback: rely on PATH at unit-start time. The systemd unit will
    # fail clearly if the binary isn't found.
    return "/usr/local/bin/hop3-rootd"


SERVICE_TEMPLATE = """\
[Unit]
Description=Hop3 privileged operations daemon
Documentation=https://github.com/abilian/hop3/blob/main/notes/adrs/041-privileged-operations-agent.md
Requires=hop3-rootd.socket
After=hop3-rootd.socket network.target

[Service]
Type=notify
ExecStart={daemon_command}
Restart=on-failure
RestartSec=2s

# --- Capability scoping (only nft needs CAP_NET_ADMIN) ---
User=root
CapabilityBoundingSet=CAP_NET_ADMIN
AmbientCapabilities=CAP_NET_ADMIN
NoNewPrivileges=true

# --- Filesystem isolation ---
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/hop3-rootd /var/log/hop3-rootd
PrivateTmp=true
PrivateDevices=true
PrivateMounts=true

# --- Kernel-surface protection ---
ProtectKernelModules=true
ProtectKernelTunables=true
ProtectKernelLogs=true
ProtectClock=true
ProtectHostname=true
ProtectProc=invisible
ProtectControlGroups=true
LockPersonality=true
MemoryDenyWriteExecute=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true

# --- Network surface (UDS for IPC, NETLINK for nft) ---
RestrictAddressFamilies=AF_UNIX AF_NETLINK
IPAddressDeny=any

# --- Syscall filter ---
SystemCallFilter=@system-service @network-io
SystemCallFilter=~@privileged @resources @debug @cpu-emulation @keyring
SystemCallErrorNumber=EPERM
SystemCallArchitectures=native

# --- Resource limits ---
MemoryMax=128M
TasksMax=16
LimitNOFILE=1024

# --- Directories (systemd auto-creates with right perms) ---
RuntimeDirectory=hop3-rootd
RuntimeDirectoryMode=0755
StateDirectory=hop3-rootd
StateDirectoryMode=0700
LogsDirectory=hop3-rootd
LogsDirectoryMode=0700

[Install]
WantedBy=multi-user.target
"""


SOCKET_CONTENT = """\
[Unit]
Description=Hop3 privileged operations daemon — socket
PartOf=hop3-rootd.service

[Socket]
ListenStream=/run/hop3-rootd/socket
SocketMode=0660
SocketUser=root
SocketGroup=hop3
RemoveOnStop=true

[Install]
WantedBy=sockets.target
"""


LOGROTATE_CONTENT = """\
/var/log/hop3-rootd/audit.log {
    daily
    rotate 90
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root hop3
    postrotate
        systemctl kill -s SIGUSR1 hop3-rootd >/dev/null 2>&1 || true
    endscript
}
"""


# --- Install / migrate ---------------------------------------------------


def setup_rootd() -> None:
    """Install hop3-rootd: units, logrotate, dirs, initial state, nft table.

    Idempotent: safe to re-run on an existing install. Per ADR 041 §12,
    if `/etc/sudoers.d/hop3` is present at the start of this function we
    keep it until rootd is verified up — the point of no return is the
    final unlink call below.
    """
    print_info("Installing hop3-rootd (privileged operations daemon)...")

    daemon_command = _resolve_daemon_command()

    # 1) Drop systemd units.
    SERVICE_PATH.write_text(SERVICE_TEMPLATE.format(daemon_command=daemon_command))
    SERVICE_PATH.chmod(0o644)
    SOCKET_PATH.write_text(SOCKET_CONTENT)
    SOCKET_PATH.chmod(0o644)
    print_success(f"systemd units installed at {SERVICE_PATH} and {SOCKET_PATH}")

    # 2) Logrotate.
    LOGROTATE_PATH.write_text(LOGROTATE_CONTENT)
    LOGROTATE_PATH.chmod(0o644)
    print_success(f"logrotate config installed at {LOGROTATE_PATH}")

    # 3) Directories. systemd's RuntimeDirectory= / StateDirectory= /
    # LogsDirectory= will (re)create these on each start with the
    # configured perms; the initial mkdir here is just so state-init
    # below works on a fresh box.
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.chmod(0o700)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.chmod(0o700)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.chmod(0o755)

    # 4) Initial state.json (idempotent — only created if missing).
    if not STATE_FILE.exists():
        try:
            run_cmd(
                [daemon_command, "--init-state", "--state-path", str(STATE_FILE)],
                check=True,
            )
            print_success(f"initial state.json created at {STATE_FILE}")
        except (CommandError, FileNotFoundError) as e:
            # The hop3-rootd binary may not be on PATH yet; fall back to
            # a hand-written empty state. This matches what --init-state
            # would produce.
            print_warning(
                f"could not run --init-state ({e}); creating fallback state.json"
            )
            STATE_FILE.write_text('{"version": 1, "rules": []}\n')
            STATE_FILE.chmod(0o600)

    # 5) Initial nftables table. Idempotent — `nft add table` with `-c`
    # just verifies; using add and tolerating EEXIST.
    _ensure_inet_hop3_table()

    # 6) Enable + (re)start units. systemd resolves ordering via the unit's
    # Requires=/After= directives, so we can pass both names per call.
    run_cmd(["systemctl", "daemon-reload"], check=False)
    run_cmd(
        ["systemctl", "enable", "hop3-rootd.socket", "hop3-rootd.service"],
        check=False,
    )
    result = run_cmd(
        ["systemctl", "restart", "hop3-rootd.socket", "hop3-rootd.service"],
        check=False,
    )
    if result.returncode != 0:
        print_warning("hop3-rootd.service failed to start")
        print_detail("Check status: journalctl -u hop3-rootd -n 50")
        # Don't proceed to the sudoers retirement on failure — keep the
        # fallback in place.
        return

    print_success("hop3-rootd is running")

    # 7) Migration: retire the legacy sudoers fragment if present.
    # Point of no return — only do this AFTER rootd has started OK.
    _retire_sudoers_fragment()


def _ensure_inet_hop3_table() -> None:
    """Create the `inet hop3` table+chain if missing. Idempotent."""
    if not cmd_exists("nft"):
        print_warning("nft not found on PATH; skipping inet hop3 table creation")
        print_detail("install nftables: apt install nftables / dnf install nftables")
        return

    # Add table — tolerate "File exists".
    result = run_cmd(["nft", "add", "table", "inet", "hop3"], check=False, capture=True)
    if result.returncode != 0 and "File exists" not in result.stderr:
        print_warning(f"could not create nftables table inet hop3: {result.stderr}")
        return

    # Add input chain — tolerate "File exists".
    result = run_cmd(
        [
            "nft",
            "add",
            "chain",
            "inet",
            "hop3",
            "input",
            "{",
            "type",
            "filter",
            "hook",
            "input",
            "priority",
            "filter",
            ";",
            "policy",
            "accept",
            ";",
            "}",
        ],
        check=False,
        capture=True,
    )
    if result.returncode != 0 and "File exists" not in result.stderr:
        print_warning(f"could not create inet hop3 input chain: {result.stderr}")
        return

    print_success("inet hop3 nftables table ready")


def _retire_sudoers_fragment() -> None:
    """Remove `/etc/sudoers.d/hop3` if present. Logged loudly.

    Per ADR 041 §12 this is the point of no return — at this point
    hop3-rootd has been verified up. If the fragment isn't there
    (fresh install), this is a no-op.
    """
    try:
        SUDOERS_FRAGMENT.unlink()
    except FileNotFoundError:
        return  # Fresh install — nothing to retire.
    except OSError as e:
        print_warning(
            f"could not remove {SUDOERS_FRAGMENT}: {e}; "
            "operator should remove it manually after verifying rootd works"
        )
        return
    print_success(
        f"removed legacy sudoers fragment {SUDOERS_FRAGMENT} "
        "(nginx ops now go through hop3-rootd)"
    )


def uninstall_rootd() -> None:
    """Uninstall hop3-rootd. Removes units, logrotate, state, and the
    `inet hop3` table.

    Called by `hop3-install uninstall`. Not currently reachable from a
    standard `hop3-install server` run.
    """
    run_cmd(["systemctl", "disable", "--now", "hop3-rootd.service"], check=False)
    run_cmd(["systemctl", "disable", "--now", "hop3-rootd.socket"], check=False)
    for path in (SERVICE_PATH, SOCKET_PATH, LOGROTATE_PATH, STATE_FILE):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    run_cmd(["systemctl", "daemon-reload"], check=False)
    # Drop the table — uninstall removes everything.
    run_cmd(["nft", "delete", "table", "inet", "hop3"], check=False, capture=True)
    print_success("hop3-rootd uninstalled")
