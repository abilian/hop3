# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Vagrant backend for testing in virtual machines."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hop3_installer.common import find_project_root
from hop3_installer.testing.common import (
    VERBOSE,
    CommandResult,
    log_debug,
    log_error,
    log_info,
    log_success,
)

from .base import Backend


class VagrantBackend(Backend):
    """Backend for testing in Vagrant virtual machines.

    This backend runs tests inside Vagrant VMs, providing full system
    testing with systemd support.
    """

    name = "vagrant"
    supports_systemd = True

    def __init__(self, vm_name: str = "ubuntu", vagrant_dir: Path | None = None):
        """Initialize Vagrant backend.

        Args:
            vm_name: Name of the VM to use (must be defined in Vagrantfile)
            vagrant_dir: Path to directory containing Vagrantfile
        """
        self.vm_name = vm_name
        if vagrant_dir:
            self.vagrant_dir = vagrant_dir
        else:
            # Default: testing/vagrant/ subdirectory
            self.vagrant_dir = Path(__file__).parent.parent / "vagrant"

    def _run_vagrant(
        self,
        *args: str,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a vagrant command."""
        cmd = ["vagrant", *args]
        log_debug(f"Running: {' '.join(cmd)}")
        return subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            cwd=self.vagrant_dir,
        )

    def _vm_is_running(self) -> bool:
        """Check if the VM is running."""
        try:
            result = self._run_vagrant(
                "status", self.vm_name, capture_output=True, check=False
            )
            return "running" in result.stdout
        except Exception:
            return False

    def setup(self) -> bool:
        """Start Vagrant VM for testing."""
        log_info(f"Starting VM: {self.vm_name}")

        if self._vm_is_running():
            log_info(f"VM {self.vm_name} is already running")
            self._sync_files()
            return True

        try:
            if VERBOSE:
                self._run_vagrant("up", self.vm_name)
            else:
                result = self._run_vagrant(
                    "up", self.vm_name, capture_output=True, check=False
                )
                # Print only important lines
                for line in result.stdout.splitlines():
                    if "==>" in line or "error" in line.lower():
                        print(line)
                if result.returncode != 0:
                    print(result.stderr)
                    return False
        except subprocess.CalledProcessError as e:
            log_error(f"Failed to start VM: {e}")
            return False

        if self._vm_is_running():
            log_success(f"VM {self.vm_name} is running")
            self._sync_files()
            return True

        log_error(f"Failed to start VM {self.vm_name}")
        return False

    def _sync_files(self) -> None:
        """Sync files to the VM."""
        log_info("Syncing files to VM...")
        try:
            self._run_vagrant("rsync", self.vm_name, capture_output=True, check=False)
        except Exception:
            pass

    def teardown(self) -> None:
        """Destroy the Vagrant VM."""
        log_info(f"Destroying VM: {self.vm_name}")
        try:
            self._run_vagrant(
                "destroy", "-f", self.vm_name, capture_output=True, check=False
            )
        except Exception:
            pass

    def stop(self) -> None:
        """Stop the VM without destroying it."""
        log_info(f"Stopping VM: {self.vm_name}")
        try:
            self._run_vagrant("halt", self.vm_name, capture_output=True, check=False)
        except Exception:
            pass

    def run(self, command: str, *, sudo: bool = False) -> CommandResult:
        """Run a command inside the Vagrant VM."""
        if sudo:
            command = f"sudo {command}"

        result = self._run_vagrant(
            "ssh",
            self.vm_name,
            "-c",
            command,
            capture_output=True,
            check=False,
        )

        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _find_project_root(self) -> Path:
        """Find the project root directory (hop3/)."""
        return find_project_root(self.vagrant_dir)

    def upload(self, local_path: Path, remote_path: str) -> bool:
        """Upload a file to the VM.

        Note: Vagrant VMs use shared folders, so this copies to /vagrant.
        The Vagrantfile syncs the project root (hop3/) to /vagrant.
        """
        # Files are already synced via rsync/shared folders
        # Just verify the file exists
        project_root = self._find_project_root()
        rel_path = local_path.relative_to(project_root)
        result = self.run(f"test -f /vagrant/{rel_path}")
        return result.success

    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Upload a directory to the VM."""
        # Directories are already synced via rsync/shared folders
        # The Vagrantfile syncs the project root (hop3/) to /vagrant.
        project_root = self._find_project_root()
        rel_path = local_path.relative_to(project_root)
        result = self.run(f"test -d /vagrant/{rel_path}")
        return result.success

    def cleanup_cli(self) -> None:
        """Clean up CLI installation from VM."""
        log_info("Cleaning up CLI installation...")
        self.run("rm -rf ~/.hop3-cli ~/.local/bin/hop3 ~/.local/bin/hop")
        log_success("CLI cleanup complete")

    def cleanup_server(self) -> None:
        """Clean up server installation from VM."""
        log_info("Cleaning up server installation...")
        self.run("systemctl stop hop3-server uwsgi-hop3 2>/dev/null || true", sudo=True)
        self.run("rm -rf /home/hop3 /etc/hop3", sudo=True)
        self.run("userdel -r hop3 2>/dev/null || true", sudo=True)
        self.run(
            "rm -f /etc/systemd/system/hop3-server.service "
            "/etc/systemd/system/uwsgi-hop3.service",
            sudo=True,
        )
        self.run("systemctl daemon-reload", sudo=True)
        log_success("Server cleanup complete")

    def get_installer_path(self, installer_type: str) -> str:
        """Get path to installer in VM (shared folder)."""
        if installer_type == "cli":
            return "/vagrant/installer/install-cli.py"
        return "/vagrant/installer/install-server.py"
