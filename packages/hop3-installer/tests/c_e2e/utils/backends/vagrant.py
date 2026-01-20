# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Vagrant backend for testing in virtual machines."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hop3_installer.common import CommandResult, find_project_root
from utils.common import VERBOSE, log_debug, log_error, log_info, log_success

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
            # Default: look for vagrant dir in hop3-installer package
            # tests/c_e2e/utils/backends/vagrant.py -> up to package root
            pkg_root = Path(__file__).parent.parent.parent.parent.parent
            self.vagrant_dir = (
                pkg_root / "src" / "hop3_installer" / "testing" / "vagrant"
            )
            if not self.vagrant_dir.exists():
                # Fallback: try to find it relative to project root
                project_root = find_project_root(Path(__file__).parent)
                self.vagrant_dir = (
                    project_root
                    / "packages"
                    / "hop3-installer"
                    / "src"
                    / "hop3_installer"
                    / "testing"
                    / "vagrant"
                )

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

        For files within the project root, uses the shared /vagrant folder.
        For files outside the project, uses vagrant ssh to copy via stdin.
        """
        project_root = self._find_project_root()

        # Check if file is within project root (use shared folder)
        try:
            rel_path = local_path.relative_to(project_root)
            # File is in project - check it exists in shared folder
            result = self.run(f"test -f /vagrant/{rel_path}")
            if result.success:
                # Copy from shared folder to target location
                self.run(f"cp /vagrant/{rel_path} {remote_path}", sudo=True)
                return True
        except ValueError:
            pass  # File is outside project root

        # File is outside project - copy via cat/ssh
        try:
            content = local_path.read_bytes()
            # Use vagrant ssh with stdin to copy file
            result = self._run_vagrant(
                "ssh",
                self.vm_name,
                "-c",
                f"cat > {remote_path}",
                capture_output=False,
                check=False,
            )
            # Write content via a different approach - use base64
            import base64

            encoded = base64.b64encode(content).decode()
            result = self.run(
                f"echo '{encoded}' | base64 -d > {remote_path}", sudo=True
            )
            return result.success
        except Exception as e:
            log_debug(f"Failed to upload {local_path}: {e}")
            return False

    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Upload a directory to the VM.

        For directories within the project root, uses the shared /vagrant folder.
        For directories outside the project, uses tar over SSH.
        """
        project_root = self._find_project_root()

        # Check if directory is within project root (use shared folder)
        try:
            rel_path = local_path.relative_to(project_root)
            # Directory is in project - check it exists in shared folder
            result = self.run(f"test -d /vagrant/{rel_path}")
            if result.success:
                # Copy from shared folder to target location
                self.run(f"cp -r /vagrant/{rel_path} {remote_path}", sudo=True)
                self.run(f"chmod -R a+rX {remote_path}", sudo=True)
                return True
        except ValueError:
            pass  # Directory is outside project root

        # Directory is outside project - use tar over SSH
        try:
            import base64
            import tarfile
            from io import BytesIO

            # Create tar archive in memory
            tar_buffer = BytesIO()
            with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
                tar.add(local_path, arcname=local_path.name)
            tar_data = tar_buffer.getvalue()

            # Upload tar via base64 and extract
            encoded = base64.b64encode(tar_data).decode()

            # Create target directory and extract
            self.run(f"mkdir -p {remote_path}", sudo=True)
            parent_dir = str(Path(remote_path).parent)
            result = self.run(
                f"echo '{encoded}' | base64 -d | tar -xzf - -C {parent_dir}",
                sudo=True,
            )
            if result.success:
                self.run(f"chmod -R a+rX {remote_path}", sudo=True)
            return result.success
        except Exception as e:
            log_debug(f"Failed to upload directory {local_path}: {e}")
            return False

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
