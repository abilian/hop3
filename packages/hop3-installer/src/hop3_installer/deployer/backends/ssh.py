# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""SSH deployment backend for remote servers."""

from __future__ import annotations

import shlex
import subprocess
from typing import TYPE_CHECKING

from hop3_installer.common import CommandResult

from .base import DeployBackend

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_installer.deployer.config import DeployConfig

# The hop3-server venv interpreter on a standard install; it can import `hop3`
# and therefore the addon plugins.
_SERVER_VENV_PYTHON = "/home/hop3/venv/bin/python3"

# Destroy every provisioned addon through its own plugin, so each backing store
# (MySQL/PostgreSQL database + role, Redis logical db) is reclaimed the way that
# service requires. Fed to the server's interpreter on stdin.
#
# A failure to destroy one addon does not stop the others — reclaiming three of
# four beats reclaiming none — but the script still exits non-zero so the caller
# never reports a clean server it did not deliver.
_RECLAIM_ADDONS_SCRIPT = """
import sys

from hop3.core.plugins import get_addon
from hop3.orm import get_session_factory
from hop3.orm.repositories import AddonCredentialRepository

failed = []
reclaimed = 0

session = get_session_factory()()
addons = {
    (c.addon_type, c.addon_name)
    for c in AddonCredentialRepository(session=session).list_all_with_apps()
}

for addon_type, addon_name in sorted(addons):
    try:
        get_addon(addon_type, addon_name).destroy()
        print(f"reclaimed {addon_type} {addon_name}")
        reclaimed += 1
    except Exception as e:
        failed.append(f"{addon_type} {addon_name}: {e}")


def sweep_unowned():
    \"\"\"
    Drop databases Hop3 created whose records it has since lost.

    Enumerating from Hop3's own tables only finds what it still remembers, and a
    previous --clean wiped those records while leaving the databases behind — so
    the very orphans that break the next install are invisible to it.

    They are identifiable, though: Hop3 provisions a database `<name>_<type>`
    together with a companion role `<name>_<type>_user`, and that pair is the
    signature. A database somebody else put on this server has no such role, so
    it is left alone.
    \"\"\"
    try:
        import mysql.connector

        from hop3.plugins.mysql.admin import MySQLAdmin
    except Exception:
        return

    try:
        conn = mysql.connector.connect(**MySQLAdmin().get_connection_params())
    except Exception as e:
        failed.append(f"mysql sweep: could not connect: {e}")
        return

    cursor = conn.cursor()
    cursor.execute(
        \"\"\"
        SELECT d.SCHEMA_NAME FROM information_schema.SCHEMATA d
        WHERE d.SCHEMA_NAME LIKE '%%_mysql'
          AND EXISTS (SELECT 1 FROM mysql.user u
                      WHERE u.User = CONCAT(d.SCHEMA_NAME, '_user'))
        \"\"\"
    )
    orphans = [row[0] for row in cursor.fetchall()]
    for db in orphans:
        try:
            cursor.execute(f"DROP DATABASE IF EXISTS `{db}`")
            cursor.execute("DROP USER IF EXISTS %s", (db + "_user",))
            conn.commit()
            print(f"reclaimed orphaned mysql database {db}")
        except Exception as e:
            failed.append(f"mysql {db}: {e}")
    cursor.close()
    conn.close()


sweep_unowned()

if not addons and not reclaimed:
    print("no tracked addons to reclaim")

for failure in failed:
    print(f"FAILED to reclaim {failure}", file=sys.stderr)
sys.exit(1 if failed else 0)
"""


class SSHDeployBackend(DeployBackend):
    """Backend for deploying to remote servers via SSH."""

    name = "ssh"

    def __init__(self, config: DeployConfig) -> None:
        super().__init__(config)
        self._ssh_opts = [
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
        ]
        # Use an explicit identity when given (else ssh's default key/agent). This
        # threads through every ssh/scp call below since they splat _ssh_opts.
        if config.ssh_key:
            self._ssh_opts.extend(["-i", config.ssh_key])
        # Add port option if not default
        if config.ssh_port != 22:
            self._ssh_opts.extend(["-p", str(config.ssh_port)])
        self._scp_port_opts = (
            ["-P", str(config.ssh_port)] if config.ssh_port != 22 else []
        )

    def setup(self) -> bool:
        """Verify SSH connectivity to the target."""
        result = self.run("echo 'SSH OK'", check=False)
        if not result.success:
            self._report_setup_failure("SSH connectivity", result)
            return False

        # Check Python is available
        result = self.run("python3 --version", check=False)
        if not result.success:
            self._report_setup_failure("python3 availability", result)
            return False
        return True

    def _report_setup_failure(self, what: str, result: CommandResult) -> None:
        """
        Print the real reason a setup check failed — fail loud, not a bare False.

        ``StrictHostKeyChecking=accept-new`` rejects a *changed* host key (common
        for ephemeral/rebuilt targets), so that message surfaces here for the
        operator instead of being swallowed behind a generic "Failed to setup
        deployment target".
        """
        detail = (result.stderr or result.stdout or "").strip() or "(no output)"
        print(f"  ✗ {what} check failed for {self.config.ssh_target}:\n{detail}")

    def teardown(self) -> None:
        """No teardown needed for SSH."""

    def run(
        self,
        command: str,
        *,
        check: bool = True,
        stdin: str | None = None,
    ) -> CommandResult:
        """Run a command on the remote server via SSH."""
        ssh_cmd = [
            "ssh",
            *self._ssh_opts,
            self.config.ssh_target,
            command,
        ]

        result = subprocess.run(
            ssh_cmd,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )

        cmd_result = CommandResult.from_subprocess(result)
        self._raise_if_failed(cmd_result, command, check=check)
        return cmd_result

    def run_streaming(
        self, command: str, *, quiet: bool = False, log_file: Path | None = None
    ) -> int:
        """Run a command with output handling based on mode."""
        ssh_cmd = [
            "ssh",
            *self._ssh_opts,
            self.config.ssh_target,
            f"PYTHONUNBUFFERED=1 DEBIAN_FRONTEND=noninteractive {command}",
        ]

        if quiet:
            # Capture output for log file
            result = subprocess.run(
                ssh_cmd, capture_output=True, text=True, check=False
            )
            if log_file:
                self._write_log_output(
                    log_file, command, result.returncode, result.stdout, result.stderr
                )
            return result.returncode

        # Stream directly to terminal
        result = subprocess.run(ssh_cmd, check=False)  # type: ignore[assignment]
        return result.returncode

    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """Upload a file via SCP."""
        scp_cmd = [
            "scp",
            *self._scp_port_opts,
            *self._ssh_opts,
            str(local_path),
            f"{self.config.ssh_target}:{remote_path}",
        ]

        result = subprocess.run(
            scp_cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        return result.returncode == 0

    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Upload a directory via rsync."""
        # Build a shell-safe SSH options string for rsync -e.
        # rsync passes -e to popen("/bin/sh", "-c", ...) internally,
        # so every token must be shell-escaped.  shlex.join() does
        # that — it joins argv into a single string that the shell can
        # round-trip safely.
        ssh_opts_str = shlex.join(self._ssh_opts)
        rsync_cmd = [
            "rsync",
            "-avz",
            "--delete",
            "--exclude=*.pyc",
            "--exclude=__pycache__",
            "--exclude=.git",
            "--exclude=*.egg-info",
            "--exclude=.pytest_cache",
            "--exclude=dist",
            "-e",
            f"ssh {ssh_opts_str}",
            f"{local_path}/",
            f"{self.config.ssh_target}:{remote_path}/",
        ]

        result = subprocess.run(
            rsync_cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            # Fix permissions
            self.run(f"chmod -R a+rX {remote_path}", check=False)

        return result.returncode == 0

    def clean(self) -> None:
        """
        Clean the server for fresh installation.

        Addon storage is reclaimed FIRST, while Hop3 still knows what it
        provisioned. Databases live in MySQL/PostgreSQL/Redis — separate
        services, outside /home/hop3 — so wiping that directory leaves them
        behind, and the next install of an app with the same name silently
        attaches to its predecessor's data.
        """
        # Stop the apps FIRST: a running app holds an open connection to its
        # database, and PostgreSQL refuses to drop a database that anyone is
        # connected to. Reclaiming before this failed on exactly that.
        stop_commands = [
            "systemctl stop hop3-server 2>/dev/null || true",
            "systemctl stop uwsgi-hop3 2>/dev/null || true",
            "docker ps -q | xargs -r docker stop 2>/dev/null || true",
            "docker ps -aq | xargs -r docker rm 2>/dev/null || true",
        ]
        for cmd in stop_commands:
            self.run(cmd, check=False)

        # Then reclaim, while /home/hop3/hop3.db still records what to reclaim.
        self._reclaim_addon_storage()

        commands = [
            # Prune Docker networks to prevent "address pools fully subnetted" errors
            "docker network prune -f 2>/dev/null || true",
            "rm -f /etc/nginx/sites-enabled/hop3-* 2>/dev/null || true",
            "rm -f /etc/nginx/sites-available/hop3-* 2>/dev/null || true",
            "systemctl reload nginx 2>/dev/null || true",
            "rm -rf /home/hop3",
            "mkdir -p /home/hop3 && chown hop3:hop3 /home/hop3 2>/dev/null || true",
        ]

        for cmd in commands:
            self.run(cmd, check=False)

    def _reclaim_addon_storage(self) -> None:
        """
        Destroy every addon Hop3 provisioned, before its records are deleted.

        Enumerated from Hop3's own database rather than guessed from database
        names, so this drops exactly what Hop3 created and never a database
        someone else put on the box. Each addon is destroyed through its own
        plugin, so MySQL, PostgreSQL and Redis are handled the way each
        requires.

        A box with no Hop3 installed has nothing to reclaim — that is the normal
        first-install case, not a failure. But an installation we can see and
        cannot enumerate ABORTS: `--clean` promising a fresh server and silently
        leaving a previous tenant's data behind is the bug this exists to fix.
        """
        probe = self.run(
            f"test -x {_SERVER_VENV_PYTHON} && test -e /home/hop3/hop3.db",
            check=False,
        )
        if probe.returncode != 0:
            print("  → No existing Hop3 database; no addon storage to reclaim")
            return

        print("  → Reclaiming addon storage (databases) from the previous install")
        result = self.run(
            "su - hop3 -c 'set -a; . /etc/default/hop3 2>/dev/null; set +a; "
            f"{_SERVER_VENV_PYTHON} -'",
            check=False,
            stdin=_RECLAIM_ADDONS_SCRIPT,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            msg = (
                "Could not reclaim addon storage from the existing installation, "
                "so --clean cannot deliver the fresh server it promises: the old "
                "databases would survive and the next install of an app with the "
                "same name would attach to its predecessor's data.\n"
                f"{output.strip()}\n"
                "Drop the leftover databases by hand (or remove /home/hop3/hop3.db "
                "to accept keeping them), then re-run."
            )
            raise RuntimeError(msg)
        for line in output.splitlines():
            if line.strip():
                print(f"    {line.strip()}")

    def get_server_url(self) -> str:
        """Get the URL to access the server."""
        return f"http://{self.config.host}:8000"
