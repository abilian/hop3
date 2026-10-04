# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Mailpit, the sink behind the email addon's `catch` backend (ADR 054).

`hop3 server email backend catch` points the loopback Postfix at
127.0.0.1:1025, and nothing listened there: mail an app sent was queued for a
sink that did not exist, while the backend reported itself selected. Mailpit
captures it instead, and its HTTP API is what makes captured mail observable,
to an operator (`hop3 server email caught`) and to the test harness.

Installed by `--with email`, pinned by version and SHA-256, and run under the
process manager, bound to loopback only. Names here carry a ``mailpit``
prefix: the bundler inlines every installer module into one file, and
``s3.py`` already defines the generic ones.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
import tempfile
from pathlib import Path

from hop3_installer.common import (
    InstallStepError,
    has_systemd,
    print_detail,
    print_info,
    print_success,
    process_manager_pending,
    run_cmd,
)
from hop3_installer.constants import HOP3_GROUP, HOP3_USER

#: Pinned, with the SHA-256 of each archive GitHub publishes for the release
#: (each checked against a download). A bump changes all three together.
MAILPIT_VERSION = "v1.31.4"
MAILPIT_SHA256 = {
    "amd64": "30942c4605c2ca8b9f759b1bb4e3ab6a12bdfdf66e5c94644ec2c75ac41e88e7",
    "arm64": "010a346a8b9d454f6fa22d4fd2dbd5bf5eb7104688412b9c130d0ba33a3579c4",
}
MAILPIT_URL = (
    "https://github.com/axllent/mailpit/releases/download/"
    "{version}/mailpit-linux-{arch}.tar.gz"
)

MAILPIT_BIN = Path("/usr/local/bin/mailpit")
MAILPIT_DATA_DIR = Path("/var/lib/mailpit")
MAILPIT_SERVICE_FILE = Path("/etc/systemd/system/mailpit.service")
MAILPIT_SUPERVISOR_FILE = Path("/etc/supervisor/conf.d/mailpit.conf")

#: Loopback only: Mailpit's defaults bind every interface. 1025 is where the
#: catch backend's Postfix relays (hop3-rootd `_CATCH_DEFAULT_PORT`).
MAILPIT_SMTP = "127.0.0.1:1025"
MAILPIT_HTTP = "127.0.0.1:8025"

_MAILPIT_COMMAND = (
    f"{MAILPIT_BIN} --smtp {MAILPIT_SMTP} --listen {MAILPIT_HTTP} "
    f"--database {MAILPIT_DATA_DIR / 'mailpit.db'} --disable-version-check"
)


def install_mailpit() -> None:
    """
    Install Mailpit and run it under this host's process manager.

    Raises:
        CommandError, InstallStepError: a step failed.
    """
    _install_mailpit_binary()
    MAILPIT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_cmd(["chown", f"{HOP3_USER}:{HOP3_GROUP}", str(MAILPIT_DATA_DIR)])
    _start_mailpit()


def _mailpit_arch() -> str:
    machine = os.uname().machine.lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    msg = f"--with email: no Mailpit build is pinned for {machine!r} (amd64, arm64)"
    raise InstallStepError(msg)


def _install_mailpit_binary() -> None:
    """Download, verify and install the pinned Mailpit, unless it is there."""
    if MAILPIT_BIN.exists():
        result = run_cmd([str(MAILPIT_BIN), "version"], check=False)
        if MAILPIT_VERSION in (result.stdout or ""):
            print_detail(f"Mailpit {MAILPIT_VERSION} already installed")
            return

    arch = _mailpit_arch()
    url = MAILPIT_URL.format(version=MAILPIT_VERSION, arch=arch)
    print_info(f"Downloading Mailpit {MAILPIT_VERSION} ({arch})...")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "mailpit.tar.gz"
        run_cmd(["curl", "-fsSL", "-o", str(archive), url])
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != MAILPIT_SHA256[arch]:
            msg = (
                f"Mailpit archive {url} has SHA-256 {digest}, not the pinned "
                f"{MAILPIT_SHA256[arch]}: refusing to install it"
            )
            raise InstallStepError(msg)
        # One named member, read rather than extracted: no path from the
        # archive reaches the filesystem, on any Python the installer runs on.
        with tarfile.open(archive) as tar:
            member = tar.extractfile("mailpit")
            if member is None:
                msg = f"{url} has no `mailpit` file"
                raise InstallStepError(msg)
            binary = member.read()
        # Staged beside the target and moved into place, so an interrupted
        # install never leaves a truncated binary that looks installed.
        staged = MAILPIT_BIN.with_suffix(".partial")
        staged.write_bytes(binary)
        staged.chmod(0o755)
        staged.replace(MAILPIT_BIN)
    print_success(f"Mailpit {MAILPIT_VERSION} installed at {MAILPIT_BIN}")


def _start_mailpit() -> None:
    """Run Mailpit under systemd, or leave it to supervisord's program file."""
    if has_systemd():
        MAILPIT_SERVICE_FILE.write_text(f"""[Unit]
Description=Mailpit, the email catch sink for Hop3
After=network.target

[Service]
Type=simple
User={HOP3_USER}
Group={HOP3_GROUP}
ExecStart={_MAILPIT_COMMAND}
Restart=always
RestartSec=5
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
NoNewPrivileges=true
ReadWritePaths={MAILPIT_DATA_DIR}

[Install]
WantedBy=multi-user.target
""")
        run_cmd(["systemctl", "daemon-reload"])
        run_cmd(["systemctl", "enable", "mailpit"])
        run_cmd(["systemctl", "restart", "mailpit"])
        print_success("Mailpit running (systemd)")
        return

    MAILPIT_SUPERVISOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAILPIT_SUPERVISOR_FILE.write_text(f"""[program:mailpit]
command={_MAILPIT_COMMAND}
user={HOP3_USER}
autostart=true
autorestart=true
startretries=3
stdout_logfile=/var/log/mailpit.out.log
stderr_logfile=/var/log/mailpit.err.log
""")
    if process_manager_pending():
        print_info("Mailpit will start when the process manager does")
        return
    run_cmd(["supervisorctl", "reread"])
    run_cmd(["supervisorctl", "update"])
    print_success("Mailpit running (supervisord)")
