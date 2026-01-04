# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""SSH backend for demo execution on remote servers."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .base import CommandResult, DemoBackend


class SSHDemoBackend(DemoBackend):
    """Backend for executing demos on remote servers via SSH."""

    name = "ssh"

    def __init__(self, host: str, user: str = "root"):
        """Initialize SSH backend.

        Args:
            host: Server hostname or IP address
            user: SSH username (default: root)
        """
        self.host = host
        self.user = user

    @property
    def ssh_target(self) -> str:
        """Return the SSH target string (user@host)."""
        return f"{self.user}@{self.host}"

    def setup(self) -> bool:
        """Verify SSH connectivity."""
        result = self.run("echo 'SSH connection successful'", check=False)
        return result.success

    def teardown(self) -> None:
        """No cleanup needed for SSH."""
        pass

    def run(self, command: str, *, check: bool = True) -> CommandResult:
        """Run a command on the remote server via SSH."""
        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            self.ssh_target,
            command,
        ]

        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        cmd_result = CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

        if check and not cmd_result.success:
            raise RuntimeError(
                f"SSH command failed: {command}\n"
                f"Exit code: {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

        return cmd_result

    def run_streaming(self, command: str) -> int:
        """Run a command with output streamed to terminal."""
        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "BatchMode=yes",
            "-t",
            "-t",  # Force TTY allocation
            self.ssh_target,
            command,
        ]

        result = subprocess.run(ssh_cmd, check=False)
        return result.returncode

    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """Upload a file via SCP."""
        scp_cmd = [
            "scp",
            "-o",
            "StrictHostKeyChecking=no",
            str(local_path),
            f"{self.ssh_target}:{remote_path}",
        ]

        result = subprocess.run(scp_cmd, capture_output=True, check=False)
        return result.returncode == 0

    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Upload a directory via rsync."""
        rsync_cmd = [
            "rsync",
            "-avz",
            "--delete",
            "-e",
            "ssh -o StrictHostKeyChecking=no",
            f"{local_path}/",
            f"{self.ssh_target}:{remote_path}/",
        ]

        result = subprocess.run(rsync_cmd, capture_output=True, check=False)
        return result.returncode == 0

    def is_hop3_installed(self) -> bool:
        """Check if Hop3 is installed on the server."""
        result = self.run("test -f /home/hop3/venv/bin/hop-server", check=False)
        return result.success

    def get_server_ip(self) -> str:
        """Get the server IP/hostname."""
        return self.host

    def get_server_url(self) -> str:
        """Get the URL to access the Hop3 server."""
        return f"http://{self.host}:8000"

    def clean(self) -> None:
        """Clean the server for fresh installation."""
        commands = [
            "systemctl stop hop3-server 2>/dev/null || true",
            "systemctl stop uwsgi-hop3 2>/dev/null || true",
            "rm -rf /home/hop3",
            "userdel -r hop3 2>/dev/null || true",
            "groupdel hop3 2>/dev/null || true",
        ]

        for cmd in commands:
            self.run(cmd, check=False)
