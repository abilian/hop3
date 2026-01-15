# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""SSH deployment backend for remote servers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .base import CommandResult, DeployBackend

if TYPE_CHECKING:
    from hop3_installer.deployer.config import DeployConfig


class SSHDeployBackend(DeployBackend):
    """Backend for deploying to remote servers via SSH."""

    name = "ssh"

    def __init__(self, config: DeployConfig):
        super().__init__(config)
        self._ssh_opts = [
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
        ]
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
            return False

        # Check Python is available
        result = self.run("python3 --version", check=False)
        return result.success

    def teardown(self) -> None:
        """No teardown needed for SSH."""

    def run(self, command: str, *, check: bool = True) -> CommandResult:
        """Run a command on the remote server via SSH."""
        ssh_cmd = [
            "ssh",
            *self._ssh_opts,
            self.config.ssh_target,
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
                with Path(log_file).open("a") as f:
                    f.write(f"\n=== Command: {command} ===\n")
                    if result.stdout:
                        f.write(result.stdout)
                    if result.stderr:
                        f.write(f"\n--- stderr ---\n{result.stderr}")
                    f.write(f"\n=== Exit code: {result.returncode} ===\n")
            return result.returncode

        # Stream directly to terminal
        result = subprocess.run(ssh_cmd, check=False)
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
        # Build SSH options string for rsync -e
        ssh_opts_str = " ".join(self._ssh_opts)
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

    def is_hop3_installed(self) -> bool:
        """Check if Hop3 is installed."""
        result = self.run("test -f /home/hop3/venv/bin/hop3-server", check=False)
        return result.success

    def clean(self) -> None:
        """Clean the server for fresh installation."""
        commands = [
            "systemctl stop hop3-server 2>/dev/null || true",
            "systemctl stop uwsgi-hop3 2>/dev/null || true",
            "docker ps -q | xargs -r docker stop 2>/dev/null || true",
            "docker ps -aq | xargs -r docker rm 2>/dev/null || true",
            "rm -f /etc/nginx/sites-enabled/hop3-* 2>/dev/null || true",
            "rm -f /etc/nginx/sites-available/hop3-* 2>/dev/null || true",
            "systemctl reload nginx 2>/dev/null || true",
            "rm -rf /home/hop3",
            "mkdir -p /home/hop3 && chown hop3:hop3 /home/hop3 2>/dev/null || true",
        ]

        for cmd in commands:
            self.run(cmd, check=False)

    def get_server_url(self) -> str:
        """Get the URL to access the server."""
        return f"http://{self.config.host}:8000"

    def get_os_info(self) -> dict[str, str]:
        """Get OS information from the server."""
        result = self.run("cat /etc/os-release", check=False)
        if not result.success:
            return {}

        info = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                info[key] = value.strip('"')

        return info
