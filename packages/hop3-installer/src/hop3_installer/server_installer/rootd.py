# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[suppressible-exception]

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
    ServiceStartError,
    cmd_exists,
    has_systemd,
    print_detail,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)
from hop3_installer.constants import VENV_DIR

# --- Paths and content ---------------------------------------------------

SERVICE_PATH = Path("/etc/systemd/system/hop3-rootd.service")
SOCKET_PATH = Path("/etc/systemd/system/hop3-rootd.socket")
LOGROTATE_PATH = Path("/etc/logrotate.d/hop3-rootd")
SUDOERS_FRAGMENT = Path("/etc/sudoers.d/hop3")
STATE_DIR = Path("/var/lib/hop3-rootd")
STATE_FILE = STATE_DIR / "state.json"
LOG_DIR = Path("/var/log/hop3-rootd")
RUNTIME_DIR = Path("/run/hop3-rootd")
# Operator bind-volume allow-list rootd reads (ADR 046 §2 / P2.1). Must match
# hop3_rootd.mount.BIND_ALLOWLIST_PATH.
BIND_ALLOWLIST_FILE = STATE_DIR / "bind-allowlist"
# cgroup v2 unified-hierarchy marker; native [limits] need it (ADR 046 §3).
CGROUP_CONTROLLERS = Path("/sys/fs/cgroup/cgroup.controllers")


def _resolve_daemon_command() -> str:
    """Find the hop3-rootd executable. Returns an absolute path, or raises.

    We deliberately do NOT fall back to a guessed path. Writing a systemd
    unit whose ``ExecStart`` points at a non-existent binary produces a
    silent, relentless ``status=203/EXEC`` crash loop (observed in the wild:
    1600+ restarts over 9h) and leaves every deploy unable to reload nginx —
    apps stay unreachable behind the default vhost. A missing daemon is a
    deploy-blocker (ADR 041 §14), so we fail the install loudly here instead.
    The operator must install hop3-rootd into the server venv first (see
    ``install_rootd_package``), then re-run.
    """
    # Common installation locations to probe in order.
    candidates = [
        VENV_DIR / "bin" / "hop3-rootd",  # the server venv (where we install it)
        Path("/usr/local/bin/hop3-rootd"),
        Path("/opt/hop3/.venv/bin/hop3-rootd"),  # production venv
        Path("/home/hop3/.venv/bin/hop3-rootd"),  # legacy
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return str(c)
    searched = ", ".join(str(c) for c in candidates)
    msg = (
        f"hop3-rootd binary not found (looked in: {searched}). The daemon "
        "package was not installed. Refusing to write a systemd unit with a "
        "non-existent ExecStart — it would crash-loop with status=203/EXEC "
        "and break every deploy. Install hop3-rootd into the server venv "
        "(see install_rootd_package) and re-run."
    )
    raise ServiceStartError(msg)


# NOTE — v0.6 hardening debt (tracked in notes/v0.6-rootd-hardening.md):
# This unit intentionally runs with MINIMAL sandboxing. The original heavy
# hardening (ProtectHome, ProtectSystem=strict, CapabilityBoundingSet, seccomp
# SystemCallFilter, namespace restrictions, MemoryDenyWriteExecute) was found to
# be fundamentally incompatible with rootd's role as the privileged executor of
# THREE external tools — nft, nginx (`-t` / `-s reload`), and systemctl. Each
# layer broke a different tool, and because the daemon never even started under
# it (203/EXEC), none of it was ever exercised:
#   - ProtectHome=true        -> 203/EXEC: the venv interpreter under /home is
#                                hidden from the unit's namespace at execve.
#   - ProtectSystem=strict    -> nginx -t can't write /var/log/nginx, /run.
#   - CapabilityBoundingSet=  -> drops CAP_DAC_OVERRIDE, so `nginx -t` (run as
#       CAP_NET_ADMIN only      root) gets EACCES on nginx's www-data error log.
# Re-introduce hardening in v0.6, designed and tested against ALL three tools,
# and relocate the daemon out of the hop3-writable /home venv (the open
# hop3->root escalation). Until then this matches the proven-working container
# model (rootd as a plain root daemon under supervisor). Defence-in-depth is
# still provided at the application layer by the exec wrapper's absolute-path
# binary allow-list.
SERVICE_TEMPLATE = """\
[Unit]
Description=Hop3 privileged operations daemon
Documentation=https://github.com/abilian/hop3/blob/main/notes/adrs/041-privileged-operations-agent.md
Requires=hop3-rootd.socket
After=hop3-rootd.socket network.target
# Cap the restart loop so a persistently-failing daemon enters `failed` and
# surfaces, rather than silently restarting forever (a misconfigured unit once
# looped ~1620 times before anyone noticed). Install-time failures are also
# caught by _verify_rootd_running.
#
# This minimal unit is ALSO what currently permits the ADR 046 Phase 2 ops:
# cgroup writes (`cgroup.*`, native [limits]) need ProtectControlGroups to stay
# false/unset, and bind/tmpfs mounts (`mount.*`, native [[volumes]]) need the
# daemon in the host mount namespace (no PrivateMounts). The v0.6 hardening
# redesign must preserve both — see ADR 041 §18.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=notify
ExecStart={daemon_command}
Restart=on-failure
RestartSec=2s
User=root

# Directories (systemd auto-creates with the right perms).
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


BIND_ALLOWLIST_CONTENT = """\
# hop3-rootd bind-volume allow-list (ADR 046 §2 / P2.1).
# One absolute host-path prefix per line; '#' and blank lines are ignored.
# A [[volumes]] entry with type = "bind" is permitted only if its source is at
# or below one of these prefixes. DEFAULT-DENY: with no prefixes listed, every
# bind volume is refused. Keep this conservative — a bind mounts host data into
# an app, so only add paths you intend apps to reach. Example:
#   /srv/shared
#   /data/exports
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

    The hop3-rootd binary must already be installed (see
    ``install_rootd_package``): this raises ``ServiceStartError`` up front if it
    isn't, on systemd *and* non-systemd hosts — the process manager needs it
    either way, and a dead daemon is a deploy-blocker, not a warning.

    On systemd hosts this then installs+enables+starts the units and raises if
    the daemon doesn't come up. On non-systemd hosts it does the host prep and
    leaves *activation* to the process manager (e.g. the demo runs the daemon
    under supervisor), returning without starting anything itself.
    """
    print_info("Installing hop3-rootd (privileged operations daemon)...")

    daemon_command = _resolve_daemon_command()
    systemd = has_systemd()

    # 1) Drop systemd units (only meaningful where systemd is PID 1; under
    # another init the process manager starts the daemon — see step 6).
    if systemd:
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

    # 5b) Default-deny bind allow-list + cgroup v2 host check (ADR 046 P2).
    # Both run on systemd and non-systemd hosts (before the activation branch
    # below returns), since rootd runs on both.
    _ensure_bind_allowlist()
    _check_cgroup_v2()

    # 6) Activation.
    if not systemd:
        print_info(
            "systemd not detected (PID 1 is not systemd); skipping unit "
            "activation. The process manager must start the daemon, e.g.:"
        )
        print_detail(f"{daemon_command} --socket-path {RUNTIME_DIR}/socket")
        print_detail("(the demo harness runs it under supervisor)")
        return

    # systemd resolves ordering via the unit's Requires=/After= directives,
    # so we can pass both names per call.
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
        msg = (
            f"hop3-rootd failed to start (systemctl restart returned "
            f"{result.returncode}). It is required by the deploy path "
            "(nginx reloads). Inspect: journalctl -u hop3-rootd -n 50"
        )
        raise ServiceStartError(msg)

    _verify_rootd_running()
    print_success("hop3-rootd is running")

    # 7) Migration: retire the legacy sudoers fragment if present.
    # Point of no return — only do this AFTER rootd has verified up.
    _retire_sudoers_fragment()


def _verify_rootd_running() -> None:
    """Confirm the daemon actually came up — not just that restart returned 0.

    A 'successful' install with a dead daemon is the silent failure that
    leaves deploys unable to reload nginx. We check the listening socket
    exists and the socket unit is active, and raise otherwise.
    """
    socket_path = RUNTIME_DIR / "socket"
    active = run_cmd(
        ["systemctl", "is-active", "--quiet", "hop3-rootd.socket"], check=False
    )
    if active.returncode != 0 or not socket_path.exists():
        present = "present" if socket_path.exists() else "missing"
        msg = (
            f"hop3-rootd did not come up: socket {socket_path} is {present}, "
            f"`systemctl is-active hop3-rootd.socket` returned "
            f"{active.returncode}. Inspect: journalctl -u hop3-rootd -n 50"
        )
        raise ServiceStartError(msg)


def _ensure_bind_allowlist() -> None:
    """Create the default-deny bind allow-list file if missing (idempotent).

    rootd reads this to authorize `[[volumes]]` bind sources (ADR 046 §2);
    absent or empty = deny all. We ship a commented template so operators can
    discover where to add prefixes, but never pre-allow anything.
    """
    if BIND_ALLOWLIST_FILE.exists():
        return
    BIND_ALLOWLIST_FILE.write_text(BIND_ALLOWLIST_CONTENT)
    BIND_ALLOWLIST_FILE.chmod(0o600)
    print_success(f"bind allow-list created (default-deny) at {BIND_ALLOWLIST_FILE}")


def _check_cgroup_v2() -> None:
    """Warn loudly at install time if the host lacks a cgroup v2 hierarchy.

    Native `[limits]` (memory/cpu/processes caps, ADR 046 §3) need the cgroup
    v2 unified hierarchy. Surfacing the gap here means a `[limits]` app fails at
    install-time diagnosis rather than only at first deploy. Not fatal — a box
    may run only Docker apps (limits enforced by the container runtime) or no
    `[limits]` apps at all.
    """
    if CGROUP_CONTROLLERS.exists():
        print_success(
            "cgroup v2 unified hierarchy present (native [limits] enforceable)"
        )
        return
    print_warning(
        f"no cgroup v2 unified hierarchy at {CGROUP_CONTROLLERS.parent}; native "
        "[limits] (memory/cpu/processes caps) cannot be enforced on this host"
    )
    print_detail(
        "boot with systemd.unified_cgroup_hierarchy=1, or use the Docker builder "
        "for apps that declare [limits]"
    )


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
    for path in (
        SERVICE_PATH,
        SOCKET_PATH,
        LOGROTATE_PATH,
        STATE_FILE,
        BIND_ALLOWLIST_FILE,
    ):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    run_cmd(["systemctl", "daemon-reload"], check=False)
    # Drop the table — uninstall removes everything.
    run_cmd(["nft", "delete", "table", "inet", "hop3"], check=False, capture=True)
    print_success("hop3-rootd uninstalled")
