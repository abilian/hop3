# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Server-side test runner - executes tests ON the server via SSH.

This module implements true E2E testing by:
1. Connecting to the server via SSH
2. Uploading test app source to the server
3. Running `hop3 deploy` directly on the server
4. Verifying the app works
5. Cleaning up

This is exactly how a real user with SSH access would deploy apps.
"""

from __future__ import annotations

import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import paramiko
from rich.console import Console

if TYPE_CHECKING:
    from .config import TestConfig


@dataclass
class AppTestResult:
    """Result of testing a single app."""

    app_name: str
    passed: bool
    duration: float
    error: str | None = None
    deploy_output: str = ""
    http_status: int | None = None


@dataclass
class ServerTestResult:
    """Result of running all tests on the server."""

    total: int
    passed: int
    failed: int
    skipped: int
    duration: float
    results: list[AppTestResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0


class SSHConnection:
    """Manages SSH connection to the server."""

    def __init__(self, host: str, user: str = "root", port: int = 22):
        self.host = host
        self.user = user
        self.port = port
        self._client: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None

    def connect(self) -> None:
        """Establish SSH connection."""
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            hostname=self.host,
            port=self.port,
            username=self.user,
            look_for_keys=True,
            allow_agent=True,
        )
        self._sftp = self._client.open_sftp()

    def close(self) -> None:
        """Close SSH connection."""
        if self._sftp:
            self._sftp.close()
        if self._client:
            self._client.close()

    def run(self, cmd: str, timeout: int = 300) -> tuple[int, str, str]:
        """Run command on server.

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if not self._client:
            raise RuntimeError("Not connected")

        _stdin, stdout, stderr = self._client.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return exit_code, stdout.read().decode(), stderr.read().decode()

    def upload_directory(self, local_path: Path, remote_path: str) -> None:
        """Upload a directory to the server via tarball."""
        if not self._client or not self._sftp:
            raise RuntimeError("Not connected")

        # Create tarball locally
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tarball_path = Path(tmp.name)

        try:
            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(local_path, arcname=local_path.name)

            # Upload tarball
            remote_tarball = f"/tmp/{local_path.name}.tar.gz"
            self._sftp.put(str(tarball_path), remote_tarball)

            # Extract on server
            self.run(f"mkdir -p {remote_path}")
            self.run(f"tar -xzf {remote_tarball} -C {remote_path}")
            self.run(f"rm {remote_tarball}")

        finally:
            tarball_path.unlink(missing_ok=True)

    def __enter__(self) -> SSHConnection:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class ServerTestRunner:
    """Runs tests directly on the server via SSH.

    This is the proper E2E approach - tests run exactly as a real user
    would deploy apps: via SSH on the server itself.
    """

    def __init__(
        self,
        host: str,
        config: TestConfig,
        project_root: Path,
        console: Console | None = None,
    ):
        self.host = host
        self.config = config
        self.project_root = project_root
        self.console = console or Console()
        self._ssh: SSHConnection | None = None

    def run_all(self) -> ServerTestResult:
        """Run all configured test suites."""
        start_time = time.time()
        results: list[AppTestResult] = []

        try:
            # Connect to server
            self.console.print(f"Connecting to {self.host}...")
            self._ssh = SSHConnection(self.host)
            self._ssh.connect()
            self.console.print("  [green]Connected[/green]")

            # Create temp directory on server for test apps
            self._ssh.run("mkdir -p /tmp/hop3-test-apps")

            # Run test apps
            if "test-apps" in self.config.suites:
                results.extend(self._run_test_apps())

            # Run demos
            if "demos" in self.config.suites:
                results.extend(self._run_demos())

        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return ServerTestResult(
                total=0,
                passed=0,
                failed=1,
                skipped=0,
                duration=time.time() - start_time,
                results=[
                    AppTestResult(
                        app_name="setup",
                        passed=False,
                        duration=0,
                        error=str(e),
                    )
                ],
            )

        finally:
            # Cleanup
            if self._ssh:
                self._ssh.run("rm -rf /tmp/hop3-test-apps")
                self._ssh.close()

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)

        return ServerTestResult(
            total=len(results),
            passed=passed,
            failed=failed,
            skipped=0,
            duration=time.time() - start_time,
            results=results,
        )

    def _run_test_apps(self) -> list[AppTestResult]:
        """Run test apps from apps/test-apps/."""
        results = []
        test_apps_dir = self.project_root / "apps" / "test-apps"

        if not test_apps_dir.exists():
            self.console.print(
                f"[yellow]Test apps directory not found: {test_apps_dir}[/yellow]"
            )
            return results

        # Find all test apps (directories with Procfile or hop3.toml)
        apps = self._find_test_apps(test_apps_dir)
        self.console.print(f"\nFound {len(apps)} test apps")

        for app_path in apps:
            result = self._run_single_app(app_path)
            results.append(result)

            icon = "[green]✓[/green]" if result.passed else "[red]✗[/red]"
            if result.passed:
                self.console.print(f"  {icon} {result.app_name}")
            else:
                self.console.print(f"  {icon} {result.app_name}: {result.error}")

            if self.config.fail_fast and not result.passed:
                break

        return results

    def _run_demos(self) -> list[AppTestResult]:
        """Run demos from demos/."""
        results = []
        demos_dir = self.project_root / "demos"

        if not demos_dir.exists():
            self.console.print(
                f"[yellow]Demos directory not found: {demos_dir}[/yellow]"
            )
            return results

        # Find demos that have an 'app' subdirectory
        demos = []
        for item in sorted(demos_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                app_dir = item / "app"
                if app_dir.exists() and (app_dir / "Procfile").exists():
                    demos.append(app_dir)

        self.console.print(f"\nFound {len(demos)} demos")

        for app_path in demos:
            result = self._run_single_app(app_path, prefix="demo-")
            results.append(result)

            icon = "[green]✓[/green]" if result.passed else "[red]✗[/red]"
            if result.passed:
                self.console.print(f"  {icon} {result.app_name}")
            else:
                self.console.print(f"  {icon} {result.app_name}: {result.error}")

            if self.config.fail_fast and not result.passed:
                break

        return results

    def _find_test_apps(self, base_dir: Path) -> list[Path]:
        """Find test app directories."""
        apps = []
        for item in sorted(base_dir.iterdir()):
            if not item.is_dir():
                continue
            if item.name.startswith(".") or item.name.startswith("xxx-"):
                continue
            # Must have Procfile or hop3.toml
            if (item / "Procfile").exists() or (item / "hop3.toml").exists():
                apps.append(item)
        return apps

    def _run_single_app(self, app_path: Path, prefix: str = "") -> AppTestResult:
        """Deploy and test a single app on the server."""
        start_time = time.time()
        app_name = f"{prefix}{app_path.name}-{int(time.time())}"

        if not self._ssh:
            return AppTestResult(
                app_name=app_name,
                passed=False,
                duration=0,
                error="Not connected",
            )

        try:
            # Upload app to server
            remote_app_path = f"/tmp/hop3-test-apps/{app_path.name}"
            self._ssh.upload_directory(app_path, "/tmp/hop3-test-apps")

            # Deploy app on server
            exit_code, stdout, stderr = self._ssh.run(
                f"sudo -u hop3 /home/hop3/venv/bin/hop3 deploy {app_name} {remote_app_path}",
                timeout=self.config.timeout_per_test,
            )

            deploy_output = stdout + stderr

            if exit_code != 0:
                return AppTestResult(
                    app_name=app_name,
                    passed=False,
                    duration=time.time() - start_time,
                    error=f"Deploy failed (exit {exit_code}): {stderr[:200]}",
                    deploy_output=deploy_output,
                )

            # Wait for app to start
            time.sleep(3)

            # Verify app is running - check HTTP response
            http_status = self._check_app_http(app_name)

            if http_status and 200 <= http_status < 400:
                passed = True
                error = None
            else:
                passed = False
                error = f"HTTP check failed (status: {http_status})"

            return AppTestResult(
                app_name=app_name,
                passed=passed,
                duration=time.time() - start_time,
                error=error,
                deploy_output=deploy_output,
                http_status=http_status,
            )

        except Exception as e:
            return AppTestResult(
                app_name=app_name,
                passed=False,
                duration=time.time() - start_time,
                error=str(e),
            )

        finally:
            # Cleanup: destroy the app
            if self._ssh:
                self._ssh.run(
                    f"sudo -u hop3 /home/hop3/venv/bin/hop3 app:destroy {app_name} -y",
                    timeout=60,
                )
                # Remove uploaded files
                self._ssh.run(f"rm -rf /tmp/hop3-test-apps/{app_path.name}")

    def _check_app_http(self, app_name: str) -> int | None:
        """Check if app responds to HTTP requests."""
        if not self._ssh:
            return None

        # Try to get HTTP status via curl on server
        # Apps are accessible via {app_name}.localhost or through nginx
        exit_code, stdout, stderr = self._ssh.run(
            f"curl -s -o /dev/null -w '%{{http_code}}' -H 'Host: {app_name}.localhost' http://localhost:80/ 2>/dev/null || echo '000'",
            timeout=30,
        )

        try:
            return int(stdout.strip())
        except ValueError:
            return None
