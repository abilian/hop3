# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Deployment management for Hop3 installation on test servers."""

from __future__ import annotations

import select
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from rich.console import Console

    from .config import Config, DeploymentConfig


@dataclass
class DeploymentResult:
    """Result of a deployment operation."""

    success: bool
    duration: float
    log_output: str
    error: str | None = None
    server_url: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def summary(self) -> str:
        """Get a summary of the deployment result."""
        status = "SUCCESS" if self.success else "FAILED"
        return f"Deployment {status} in {self.duration:.1f}s"


class DeploymentError(Exception):
    """Error during deployment."""


class DeploymentManager:
    """Manages Hop3 deployment to test servers."""

    REPO_URL = "https://github.com/abilian/hop3.git"

    def __init__(
        self,
        host: str,
        config: DeploymentConfig,
        repo_path: Path | None = None,
        verbose: bool = False,
        console: Console | None = None,
    ):
        """Initialize deployment manager.

        Args:
            host: Target server hostname or IP.
            config: Deployment configuration.
            repo_path: Path to existing Hop3 repo. If None, will clone fresh.
            verbose: Enable verbose output with streaming logs.
            console: Rich console for output.
        """
        self.host = host
        self.config = config
        self.repo_path = repo_path
        self.verbose = verbose
        self.console = console
        self._temp_dir: Path | None = None
        self._log_buffer: list[str] = []

    def clone_repo(self, target_dir: Path | None = None) -> Path:
        """Clone the Hop3 repository.

        Args:
            target_dir: Directory to clone into. Creates temp dir if None.

        Returns:
            Path to the cloned repository.
        """
        if target_dir is None:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="hop3-test-"))
            target_dir = self._temp_dir / "hop3"

        self._log(f"Cloning Hop3 repository to {target_dir}")

        cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            self.config.branch,
            self.REPO_URL,
            str(target_dir),
        ]

        if self.verbose and self.console:
            # Stream git clone output
            self.console.print(
                f"    Running: git clone --branch {self.config.branch} ..."
            )
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            stdout_lines = []
            if process.stdout:
                for line in process.stdout:
                    line = line.rstrip()
                    stdout_lines.append(line)
                    self.console.print(f"    {line}")
            process.wait()
            returncode = process.returncode
            stderr = ""
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            returncode = result.returncode
            stderr = result.stderr

        if returncode != 0:
            self._log(f"Clone failed: {stderr}")
            msg = f"Failed to clone repository: {stderr}"
            raise DeploymentError(msg)

        self._log(f"Cloned branch '{self.config.branch}' successfully")
        self.repo_path = target_dir
        return target_dir

    def deploy(self) -> DeploymentResult:
        """Run hop3-deploy to install Hop3 on the target server.

        Returns:
            DeploymentResult with outcome and logs.
        """
        start_time = time.time()

        try:
            # Ensure we have a repo path
            if self.repo_path is None:
                self.clone_repo()

            # Build hop3-deploy command
            cmd = self._build_deploy_command()
            self._log(f"Running: {' '.join(cmd)}")

            # Run deployment - use streaming output in verbose mode
            if self.verbose and self.console:
                returncode, stdout, stderr = self._run_with_streaming(cmd)
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=self.repo_path,
                    check=False,
                    timeout=1800,  # 30 minute timeout
                )
                returncode = result.returncode
                stdout = result.stdout
                stderr = result.stderr

            duration = time.time() - start_time
            self._log(stdout)

            if returncode != 0:
                self._log(f"Deployment failed: {stderr}")
                # Extract meaningful error from stderr
                error_msg = self._extract_error_message(stderr, stdout)
                return DeploymentResult(
                    success=False,
                    duration=duration,
                    log_output=self._get_log(),
                    error=error_msg,
                )

            # Verify installation
            server_url = f"http://{self.host}:8000"
            verified, verify_error = self._verify_installation(server_url)
            if not verified:
                return DeploymentResult(
                    success=False,
                    duration=duration,
                    log_output=self._get_log(),
                    error=f"Installation verification failed: {verify_error}",
                    server_url=server_url,
                )

            self._log("Deployment completed successfully")
            return DeploymentResult(
                success=True,
                duration=duration,
                log_output=self._get_log(),
                server_url=server_url,
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return DeploymentResult(
                success=False,
                duration=duration,
                log_output=self._get_log(),
                error="Deployment timed out after 30 minutes",
            )

        except Exception as e:
            duration = time.time() - start_time
            return DeploymentResult(
                success=False,
                duration=duration,
                log_output=self._get_log(),
                error=str(e),
            )

    def _build_deploy_command(self) -> list[str]:
        """Build the hop3-deploy command with appropriate flags."""
        cmd = [
            "uv",
            "run",
            "hop3-deploy",
            "--host",
            self.host,
        ]

        if self.config.use_local_code:
            cmd.append("--local")

        if self.config.clean_before:
            cmd.append("--clean")

        if self.config.verbose:
            cmd.append("--verbose")

        if self.config.domain:
            cmd.extend(["--admin-domain", self.config.domain])

        if self.config.acme_email:
            cmd.extend(["--acme-email", self.config.acme_email])

        # Add features (docker, mysql, redis, etc.)
        if self.config.features:
            cmd.extend(["--with", ",".join(self.config.features)])

        return cmd

    def _verify_installation(
        self,
        server_url: str,
        timeout: int = 60,
        retries: int = 6,
    ) -> tuple[bool, str]:
        """Verify that hop3-server is running and responding.

        Checks:
        1. GET / - should redirect (302/303) to /auth/login or /dashboard
        2. POST /rpc - should respond to JSON-RPC requests

        Args:
            server_url: URL to the hop3-server.
            timeout: Request timeout in seconds.
            retries: Number of retry attempts.

        Returns:
            Tuple of (success, error_details).
        """
        self._log(f"Verifying installation at {server_url}")
        last_error = ""

        for attempt in range(retries):
            try:
                # Check 1: GET / should redirect
                response = httpx.get(
                    f"{server_url}/",
                    timeout=timeout,
                    follow_redirects=False,
                )
                if response.status_code in {302, 303, 307, 308}:
                    self._log(f"Root redirect working (HTTP {response.status_code})")
                elif response.status_code == 200:
                    self._log("Root returned 200 OK")
                else:
                    last_error = f"Root check returned HTTP {response.status_code}"
                    self._log(f"Attempt {attempt + 1}: {last_error}")
                    if attempt < retries - 1:
                        time.sleep(10)
                    continue

                # Check 2: POST /rpc should respond (even errors mean server is up)
                # The RPC uses a custom protocol: method="cli", params.cli_args=["command"]
                response = httpx.post(
                    f"{server_url}/rpc",
                    json={
                        "jsonrpc": "2.0",
                        "method": "cli",
                        "params": {
                            "cli_args": ["ping"],
                            "extra_args": {},
                        },
                        "id": 1,
                    },
                    timeout=timeout,
                )

                # Any response from the RPC endpoint means the server is running
                # 200 = success, 401/403 = auth required, 404 = command not found
                # Even 500 with a response body means the server is processing requests
                if response.status_code in {200, 401, 403, 404}:
                    self._log(f"RPC endpoint responding (HTTP {response.status_code})")
                    return True, ""

                # 500 with response body also means server is running (just erroring)
                if response.status_code == 500 and response.text:
                    self._log(
                        "RPC endpoint responding with error (HTTP 500) - server is running"
                    )
                    return True, ""

                last_error = f"RPC check returned HTTP {response.status_code}: {response.text[:200]}"
                self._log(f"Attempt {attempt + 1}: {last_error}")

            except httpx.ConnectError as e:
                last_error = f"Connection refused - server may not be running: {e}"
                self._log(f"Attempt {attempt + 1}: {last_error}")

            except httpx.TimeoutException as e:
                last_error = f"Request timed out after {timeout}s: {e}"
                self._log(f"Attempt {attempt + 1}: {last_error}")

            except httpx.RequestError as e:
                last_error = f"Request error: {type(e).__name__}: {e}"
                self._log(f"Attempt {attempt + 1}: {last_error}")

            if attempt < retries - 1:
                time.sleep(10)

        self._log("Installation verification failed after all retries")
        return False, last_error

    def cleanup(self) -> None:
        """Clean up temporary files."""
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
            self._temp_dir = None

    def _run_with_streaming(self, cmd: list[str]) -> tuple[int, str, str]:
        """Run command with streaming output to console.

        Args:
            cmd: Command to run.

        Returns:
            Tuple of (returncode, stdout, stderr).
        """
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.repo_path,
            bufsize=1,  # Line buffered
        )

        # Use select to read from both stdout and stderr
        while True:
            # Check if process has finished
            if process.poll() is not None:
                # Read any remaining output
                if process.stdout:
                    for line in process.stdout:
                        line = line.rstrip()
                        stdout_lines.append(line)
                        if self.console:
                            self.console.print(f"    {line}")
                if process.stderr:
                    for line in process.stderr:
                        line = line.rstrip()
                        stderr_lines.append(line)
                        if self.console:
                            self.console.print(f"    [dim]{line}[/dim]")
                break

            # Read available output
            readable = []
            if process.stdout:
                readable.append(process.stdout)
            if process.stderr:
                readable.append(process.stderr)

            if not readable:
                break

            # Use select on Unix, fallback to simple read on Windows
            try:
                ready, _, _ = select.select(readable, [], [], 0.1)
            except (ValueError, OSError):
                # Fallback for Windows or closed pipes
                ready = readable

            for stream in ready:
                line = stream.readline()
                if line:
                    line = line.rstrip()
                    if stream == process.stdout:
                        stdout_lines.append(line)
                        if self.console:
                            self.console.print(f"    {line}")
                    else:
                        stderr_lines.append(line)
                        if self.console:
                            self.console.print(f"    [dim]{line}[/dim]")

        return process.returncode or 0, "\n".join(stdout_lines), "\n".join(stderr_lines)

    def _log(self, message: str) -> None:
        """Add message to log buffer."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_buffer.append(f"[{timestamp}] {message}")

    def _get_log(self) -> str:
        """Get accumulated log output."""
        return "\n".join(self._log_buffer)

    def _extract_error_message(self, stderr: str, stdout: str) -> str:
        """Extract meaningful error message from deployment output.

        Args:
            stderr: Standard error output.
            stdout: Standard output.

        Returns:
            Cleaned up error message.
        """
        # Combine outputs for searching
        combined = (stdout or "") + "\n" + (stderr or "")
        lines = combined.strip().split("\n")

        # First, look for Python tracebacks (most useful)
        traceback_lines = []
        in_traceback = False

        for line in lines:
            if "Traceback (most recent call last):" in line:
                in_traceback = True
                traceback_lines = [line]
            elif in_traceback:
                traceback_lines.append(line)
                # End of traceback is usually an Error line
                if line.strip() and not line.startswith(" ") and "Error" in line:
                    break

        if traceback_lines:
            # Return just the last line (the actual error) for summary
            error_line = traceback_lines[-1].strip() if traceback_lines else ""
            return error_line or "\n".join(traceback_lines[-5:])

        # Look for specific error patterns
        error_indicators = [
            "Setup failed:",
            "Installation failed",
            "ImportError:",
            "ModuleNotFoundError:",
            "SyntaxError:",
            "AttributeError:",
            "failed:",
            "Error:",
        ]

        for line in reversed(lines):
            for indicator in error_indicators:
                if indicator in line:
                    return line.strip()

        # Fallback: return last meaningful line
        for line in reversed(lines[-20:]):
            line = line.strip()
            if (
                line
                and not line.startswith("warning:")
                and "VIRTUAL_ENV" not in line
                and not line.startswith("Building ")
                and not line.startswith("Built ")
                and not line.startswith("Installed ")
                and "✓" not in line
            ):
                return line

        return "Deployment failed (see diagnostics above)"


class DeploymentVerifier:
    """Verifies a Hop3 deployment is working correctly."""

    def __init__(self, host: str, port: int = 8000):
        """Initialize verifier.

        Args:
            host: Server hostname or IP.
            port: Server port.
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    def check_root(self, timeout: int = 30) -> bool:
        """Check server root endpoint (should redirect).

        Args:
            timeout: Request timeout.

        Returns:
            True if server is responding.
        """
        try:
            response = httpx.get(
                f"{self.base_url}/",
                timeout=timeout,
                follow_redirects=False,
            )
            # Accept redirects (302, 303) or 200
            return response.status_code in {200, 302, 303, 307, 308}
        except httpx.RequestError:
            return False

    def check_rpc(self, timeout: int = 30) -> bool:
        """Check RPC endpoint is responding.

        Args:
            timeout: Request timeout.

        Returns:
            True if RPC is working (any response means server is up).
        """
        try:
            response = httpx.post(
                f"{self.base_url}/rpc",
                json={
                    "jsonrpc": "2.0",
                    "method": "cli",
                    "params": {
                        "cli_args": ["ping"],
                        "extra_args": {},
                    },
                    "id": 1,
                },
                timeout=timeout,
            )
            # Any HTTP response means server is running
            # 200 = success, 401/403 = auth, 404 = command not found
            # 500 with body = server error but still running
            if response.status_code in {200, 401, 403, 404}:
                return True
            return bool(response.status_code == 500 and response.text)

        except (httpx.RequestError, ValueError):
            return False

    def run_all_checks(self) -> dict[str, bool]:
        """Run all verification checks.

        Returns:
            Dictionary of check name to result.
        """
        return {
            "root": self.check_root(),
            "rpc": self.check_rpc(),
        }


def create_deployment_manager(
    host: str,
    config: Config,
    repo_path: Path | None = None,
) -> DeploymentManager:
    """Create a DeploymentManager instance.

    Factory function for dependency injection.

    Args:
        host: Target server hostname or IP.
        config: Full configuration.
        repo_path: Optional path to existing repo.

    Returns:
        DeploymentManager instance.
    """
    return DeploymentManager(
        host=host,
        config=config.deployment,
        repo_path=repo_path,
    )
