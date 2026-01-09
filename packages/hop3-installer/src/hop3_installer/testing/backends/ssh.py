# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""SSH backend for testing on remote servers."""

from __future__ import annotations

import shlex
import subprocess
from typing import TYPE_CHECKING

from hop3_installer.testing.common import (
    DRY_RUN,
    CommandResult,
    log_debug,
    log_error,
    log_info,
    log_success,
)

from .base import Backend

if TYPE_CHECKING:
    from pathlib import Path


class SSHBackend(Backend):
    """Backend for testing on remote servers via SSH.

    This backend connects to a remote server via SSH and executes
    commands remotely. It's the most realistic test environment.
    """

    name = "ssh"
    supports_systemd = True

    def __init__(self, host: str):
        """Initialize SSH backend.

        Args:
            host: SSH target in user@hostname format
        """
        self.host = host

    def setup(self) -> bool:
        """Verify SSH connection to the remote host."""
        log_info(f"Checking SSH connection to {self.host}...")

        if DRY_RUN:
            log_success("SSH connection OK (dry-run)")
            return True

        result = self.run("echo 'SSH OK'")
        if not result.success:
            log_error(f"Cannot connect to {self.host}")
            return False

        log_success("SSH connection OK")

        # Check Python version
        log_info("Checking Python version on remote host...")
        result = self.run(
            "python3 --version 2>/dev/null || python --version 2>/dev/null"
        )
        if result.success:
            log_success(f"Remote Python: {result.stdout.strip()}")
            return True

        log_error("Python 3 not found on remote host")
        return False

    def teardown(self) -> None:
        """No teardown needed for SSH backend."""

    def run(self, command: str, *, sudo: bool = False) -> CommandResult:
        """Run a command on the remote host via SSH."""
        if sudo:
            # Use shlex.quote to safely escape the command
            command = f"sudo bash -c {shlex.quote(command)}"

        ssh_cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
            self.host,
            command,
        ]

        log_debug(f"SSH: {command}")

        if DRY_RUN:
            print(f"  [DRY-RUN] ssh {self.host} '{command}'")
            return CommandResult(0, "", "")

        result = subprocess.run(
            ssh_cmd,
            check=False,
            capture_output=True,
            text=True,
        )

        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def upload(self, local_path: Path, remote_path: str) -> bool:
        """Upload a file to the remote host via SCP."""
        scp_cmd = [
            "scp",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            str(local_path),
            f"{self.host}:{remote_path}",
        ]

        log_debug(f"SCP: {local_path} -> {self.host}:{remote_path}")

        if DRY_RUN:
            print(f"  [DRY-RUN] scp {local_path} {self.host}:{remote_path}")
            return True

        result = subprocess.run(scp_cmd, check=False, capture_output=True, text=True)
        return result.returncode == 0

    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Upload a directory to the remote host via SCP."""
        scp_cmd = [
            "scp",
            "-r",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            str(local_path),
            f"{self.host}:{remote_path}",
        ]

        log_debug(f"SCP: {local_path} -> {self.host}:{remote_path}")

        if DRY_RUN:
            print(f"  [DRY-RUN] scp -r {local_path} {self.host}:{remote_path}")
            return True

        result = subprocess.run(scp_cmd, check=False, capture_output=True, text=True)
        return result.returncode == 0

    def cleanup_cli(self) -> None:
        """Remove CLI installation from remote host."""
        log_info("Cleaning up CLI installation...")

        # Remove installation directories and symlinks
        self.run(
            "rm -rf ~/.hop3-cli ~/.local/bin/hop3 ~/.local/bin/hop "
            "/tmp/install-cli.py /tmp/hop3-cli",
            sudo=False,
        )

        # Remove PATH additions from shell configs
        shell_configs = ["~/.bashrc", "~/.zshrc", "~/.profile", "~/.bash_profile"]
        for config in shell_configs:
            self.run(
                f"sed -i '/# Added by Hop3 CLI installer/d' {config} 2>/dev/null; "
                f"sed -i '/\\.local\\/bin/d' {config} 2>/dev/null",
                sudo=False,
            )

        log_success("CLI cleanup complete")

    def cleanup_server(self) -> None:
        """Remove server installation from remote host (thorough cleanup)."""
        log_info("Cleaning up server installation...")

        # Stop and disable services
        service_commands = [
            "systemctl stop hop3-server uwsgi-hop3 nginx postgresql 2>/dev/null || true",
            "systemctl disable hop3-server uwsgi-hop3 2>/dev/null || true",
            "rm -f /etc/systemd/system/hop3-server.service /etc/systemd/system/uwsgi-hop3.service",
            "systemctl daemon-reload",
        ]
        for cmd in service_commands:
            self.run(cmd, sudo=True)

        # Remove hop3 user and group
        user_commands = [
            "userdel -r hop3 2>/dev/null || true",
            "groupdel hop3 2>/dev/null || true",
            "gpasswd -d www-data hop3 2>/dev/null || true",
        ]
        for cmd in user_commands:
            self.run(cmd, sudo=True)

        # Detect distro for package removal
        distro_result = self.run(
            "cat /etc/os-release 2>/dev/null | grep -E '^ID=' | cut -d= -f2 | tr -d '\"'"
        )
        distro = distro_result.stdout.strip().lower() if distro_result.success else ""

        # Purge packages based on distro
        if distro in {"ubuntu", "debian"}:
            apt_env = "DEBIAN_FRONTEND=noninteractive"
            package_commands = [
                "systemctl stop postgresql nginx 2>/dev/null || true",
                "killall -9 apt apt-get dpkg 2>/dev/null || true",
                "rm -f /var/lib/apt/lists/lock /var/cache/apt/archives/lock /var/lib/dpkg/lock* 2>/dev/null || true",
                f"{apt_env} dpkg --configure -a 2>/dev/null || true",
                f"{apt_env} apt-get -f install -y 2>/dev/null || true",
                f"{apt_env} apt-get purge -y postgresql postgresql-client postgresql-contrib postgresql-common 2>/dev/null || true",
                f"{apt_env} apt-get autoremove -y 2>/dev/null || true",
                "rm -rf /var/lib/postgresql /etc/postgresql /var/log/postgresql",
                f"{apt_env} apt-get purge -y nginx nginx-common nginx-core nginx-full nginx-light 2>/dev/null || true",
                "rm -rf /etc/nginx /var/log/nginx /var/www/html",
                f"{apt_env} apt-get autoremove -y 2>/dev/null || true",
            ]
        elif distro in {"fedora", "rhel", "centos", "rocky", "almalinux"}:
            package_commands = [
                "systemctl stop postgresql nginx 2>/dev/null || true",
                "dnf remove -y postgresql postgresql-server postgresql-contrib 2>/dev/null || true",
                "rm -rf /var/lib/pgsql /etc/postgresql",
                "dnf remove -y nginx 2>/dev/null || true",
                "rm -rf /etc/nginx /var/log/nginx",
            ]
        else:
            package_commands = []
            log_debug(f"Unknown distro '{distro}', skipping package removal")

        for cmd in package_commands:
            self.run(cmd, sudo=True)

        # Remove acme.sh
        self.run(
            "rm -rf /home/hop3/.acme.sh /root/.acme.sh 2>/dev/null || true", sudo=True
        )

        # Clean up hop3 directories and configs
        cleanup_commands = [
            "rm -rf /home/hop3 /tmp/install-server.py /tmp/hop3-server",
            "rm -f /etc/nginx/sites-available/hop3* /etc/nginx/sites-enabled/hop3* 2>/dev/null || true",
            "rm -f /etc/nginx/conf.d/hop3* 2>/dev/null || true",
            "rm -rf /etc/hop3 2>/dev/null || true",
        ]
        for cmd in cleanup_commands:
            self.run(cmd, sudo=True)

        # Clean shell configs for root
        for config in ["/root/.bashrc", "/root/.profile", "/root/.bash_profile"]:
            self.run(f"sed -i '/hop3/Id' {config} 2>/dev/null || true", sudo=True)

        log_success("Server cleanup complete")
