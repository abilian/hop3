# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Base class for deployment backends."""

from __future__ import annotations

import shlex
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from hop3_installer.common import CommandResult

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_installer.deployer.config import DeployConfig


class DeployBackend(ABC):
    """Abstract base class for deployment backends."""

    name: str = "base"

    def __init__(self, config: DeployConfig) -> None:
        """
        Initialize the backend.

        Args:
            config: Deployment configuration
        """
        self.config = config

    def _raise_if_failed(
        self,
        result: CommandResult,
        command: str,
        *,
        check: bool,
    ) -> None:
        """
        Raise RuntimeError if command failed and check is True.

        Args:
            result: Command result to check
            command: Command that was executed (for error message)
            check: Whether to raise on failure
        """
        if check and not result.success:
            msg = (
                f"{self.name.upper()} command failed: {command}\n"
                f"Exit code: {result.returncode}\n"
                f"stderr: {result.stderr}"
            )
            raise RuntimeError(msg)

    def _write_log_output(
        self,
        log_file: Path,
        command: str,
        returncode: int,
        stdout: str | None,
        stderr: str | None,
    ) -> None:
        """
        Write command output to a log file.

        This is a shared helper for run_streaming() implementations.

        Args:
            log_file: Path to log file
            command: Command that was executed
            returncode: Exit code of the command
            stdout: Standard output (may be None)
            stderr: Standard error (may be None)
        """
        with log_file.open("a") as f:
            f.write(f"\n=== Command: {command} ===\n")
            if stdout:
                f.write(stdout)
            if stderr:
                f.write(f"\n--- stderr ---\n{stderr}")
            f.write(f"\n=== Exit code: {returncode} ===\n")

    @abstractmethod
    def setup(self) -> bool:
        """
        Set up the deployment target.

        For SSH, this verifies connectivity.
        For Docker, this starts the container.

        Returns:
            True if setup succeeded, False otherwise
        """

    @abstractmethod
    def teardown(self) -> None:
        """
        Clean up after deployment.

        For SSH, this is a no-op.
        For Docker, this optionally stops the container.
        """

    @abstractmethod
    def run(
        self,
        command: str,
        *,
        check: bool = True,
        stdin: str | None = None,
    ) -> CommandResult:
        """
        Run a command on the target.

        Args:
            command: Command to execute.
            check: Whether to raise on non-zero exit.
            stdin: Optional string to feed to the command's standard
                input. Use this instead of ``echo "$secret" | cmd`` for
                passwords or any other secret — the secret stays out of
                the spawned process's argv (and therefore out of
                ``ps`` / ``/proc/<pid>/cmdline``).

        Returns:
            CommandResult with returncode, stdout, stderr
        """

    def run_streaming(
        self, command: str, *, quiet: bool = False, log_file: Path | None = None
    ) -> int:
        """
        Run a command with output handling based on mode.

        Args:
            command: Command to execute
            quiet: If True, capture output to log file instead of terminal
            log_file: File to write output to (required if quiet=True)

        Returns:
            Exit code of the command
        """
        # Default implementation falls back to regular run
        result = self.run(command, check=False)

        if quiet and log_file:
            self._write_log_output(
                log_file, command, result.returncode, result.stdout, result.stderr
            )
        else:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)

        return result.returncode

    def make_root_controlled(self, remote_path: str) -> bool:
        """
        Make an uploaded tree root-owned, readable by all, writable by root only.

        hop3 installs the server and the client from it; root installs
        hop3-rootd from it, and the installer refuses a tree another user
        could change (``check_root_controlled``). ``docker cp`` keeps the
        uid the files have on this machine, and rsync leaves files it did
        not change with the owner they already had. False, with the reason
        printed.
        """
        path = shlex.quote(remote_path)
        mode = "a+rX,go-w"
        command = f"chown -R -h root:root {path} && chmod -R {mode} {path}"
        result = self.run(command, check=False)
        if not result.success:
            print(f"  ✗ {command} failed: {result.stderr.strip()}")
        return result.success

    @abstractmethod
    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """
        Upload a file to the target.

        Args:
            local_path: Local file path
            remote_path: Remote destination path

        Returns:
            True if upload succeeded
        """

    @abstractmethod
    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """
        Upload a directory to the target.

        Args:
            local_path: Local directory path
            remote_path: Remote destination path

        Returns:
            True if upload succeeded
        """

    def is_hop3_installed(self) -> bool:
        """
        Check if Hop3 is installed on the target.

        Returns:
            True if Hop3 is installed
        """
        result = self.run("test -f /home/hop3/venv/bin/hop3-server", check=False)
        return result.success

    @abstractmethod
    def clean(self) -> None:
        """Clean the target before fresh installation."""

    @abstractmethod
    def get_server_url(self) -> str:
        """
        Get the URL to access the Hop3 server.

        Returns:
            URL string (e.g., http://192.168.1.100:8000)
        """

    def start_services(self) -> None:
        """
        Start services after installation.

        For SSH targets, systemd handles services automatically.
        For Docker targets, this starts supervisor to manage services.

        The default implementation is a no-op since systemd handles services
        on real servers. Docker backend overrides this to use supervisor
        (and raises ``ServiceStartError`` if a service fails to start).
        """
        # No-op: systemd handles services on real servers
        return

    def service_restart_command(self, service: str) -> str:
        """
        The shell command that restarts a managed service on this target.

        systemd on real servers; the Docker backend overrides this for
        supervisor (its PID 1 — there is no systemd in the container). Exposed
        as a string so recovery hints can show the command that actually works
        on the target rather than a systemd-only one.
        """
        return f"systemctl restart {service}"

    def service_stop_command(self, service: str) -> str:
        """
        Stop a managed service if it is installed; exits non-zero if it fails.

        The guard makes "not installed" (a first install with `--clean`) a
        no-op, so the caller can check the result instead of `|| true`.
        """
        return (
            f"if systemctl cat {service} >/dev/null 2>&1; "
            f"then systemctl stop {service}; fi"
        )

    def service_logs_command(self, service: str) -> str:
        """
        The shell command that shows a managed service's recent logs.

        The sibling of `service_restart_command`, and needed for the same
        reason: a failed restart printed "Diagnose: journalctl -u hop3-server"
        on every target, including containers that have neither systemd nor a
        journal. Advice that cannot be followed is worse than none — it sends
        the reader looking for the wrong thing.
        """
        return f"journalctl -u {service} -n 100 --no-pager"

    def restart_service(self, service: str) -> CommandResult:
        """
        Restart a managed service, best-effort.

        Fire-and-forget by design: the caller verifies the service actually came
        back up afterwards, so a restart that "succeeded" but left a crashing
        process is caught there, not masked here.
        """
        return self.run(self.service_restart_command(service), check=False)
