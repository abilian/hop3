# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deployment session for test applications.

This module provides the main DeploymentSession class that orchestrates
the full test lifecycle: prepare, deploy, verify, cleanup.
"""

from __future__ import annotations

import os
import subprocess
import time
import traceback
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from hop3_testing.exceptions import CleanupError, DeploymentError
from hop3_testing.targets.constants import (
    E2E_TEST_SECRET_KEY,
    create_test_token,
)
from hop3_testing.util.console import Console, PrintingConsole, Verbosity
from hop3_testing.util.streaming import run_streaming

from .debug import DeploymentDebugger
from .preparation import AppPreparation
from .verification import AppVerifier

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget

    from .catalog import AppSource


class DeploymentSession:
    """Manages the deployment and testing of a test application.

    This class orchestrates:
    - Preparing the app for deployment (git init, creating tarball)
    - Deploying to the target via hop3 CLI
    - Testing the deployed app (HTTP, check scripts)
    - Cleanup

    Example:
        with DeploymentSession(app, target) as session:
            session.deploy()
            result = session.test_http_detailed()
            if result["passed"]:
                print("Test passed!")
    """

    def __init__(
        self,
        app: AppSource,
        target: DeploymentTarget,
        app_name: str | None = None,
        config: dict[str, Any] | None = None,
        console: Console | None = None,
    ):
        """Initialize deployment session.

        Args:
            app: Test application to deploy
            target: Deployment target
            app_name: Name for the deployed app (default: auto-generated)
            config: Additional configuration (debug, verbose, etc.)
            console: Console for output (default: PrintingConsole)
        """
        self.app = app
        self.target = target
        self.config = config or {}

        # Generate unique app name if not provided
        if app_name is None:
            timestamp = int(time.time())
            app_name = f"{app.name}-{timestamp}".replace("_", "-")
        self.app_name = app_name

        # Deployment state
        self.deployed = False
        self._last_deploy_error: str | None = None
        self._app_port: int | None = None

        # Console setup
        self.console = console or PrintingConsole()

        # Set verbosity from config
        verbose = self.config.get("verbose", False)
        debug = self.config.get("debug", False)
        if debug or verbose:
            self.console.set_verbosity(Verbosity.VERBOSE)

        # Delegate to specialized components
        self._preparation = AppPreparation(app, app_name)
        self._debugger = DeploymentDebugger(target, app_name, self.console)

    @property
    def temp_dir(self):
        """Get the temp directory path."""
        return self._preparation.temp_dir

    @property
    def last_deploy_error(self) -> str | None:
        """Get the last deployment error message."""
        return self._last_deploy_error

    def _build_cli_env(self) -> dict[str, str]:
        """Build environment variables for hop3 CLI commands.

        Returns:
            Environment dict with HOP3_API_URL, HOP3_SSH_KEY, HOP3_SECRET_KEY,
            and HOP3_API_TOKEN set as appropriate.
        """
        target_info = self.target.info
        env = os.environ.copy()

        # Prefer direct HTTP API URL when available (Docker without SSH port mapping)
        # Fall back to SSH tunnel for remote targets
        if target_info.api_url:
            env["HOP3_API_URL"] = target_info.api_url
            # Direct HTTP requires API token for authentication
            env["HOP3_API_TOKEN"] = create_test_token()
        else:
            # SSH tunnel provides implicit authentication via SSH keys
            env["HOP3_API_URL"] = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"
            env["HOP3_SSH_KEY"] = target_info.ssh_key or ""

        env["HOP3_SECRET_KEY"] = E2E_TEST_SECRET_KEY
        return env

    def prepare(self):
        """Prepare the application for deployment.

        Creates a temporary copy of the app with git initialized.

        Returns:
            Path to the prepared app directory
        """
        return self._preparation.prepare()

    def deploy(self, wait_time: int = 5) -> None:
        """Deploy the application to the target.

        Args:
            wait_time: Time to wait after deployment (seconds)

        Raises:
            DeploymentError: If deployment fails.
        """
        if not self._preparation.temp_dir:
            self._preparation.prepare()

        self.console.status(f"Deploying {self.app_name}...")

        try:
            # Deploy via CLI (CLI will create tarball from directory)
            self._deploy_via_cli()

            self.deployed = True

            # Wait for deployment to complete
            self.console.info(f"Waiting {wait_time}s for deployment to complete...")
            time.sleep(wait_time)

        except DeploymentError:
            raise
        except Exception as e:
            self.console.error(f"Deployment failed: {e}")
            raise DeploymentError(f"Deployment failed: {e}") from e

    def _build_deploy_error_message(
        self, returncode: int, stdout: str, stderr: str | None = None
    ) -> str:
        """Build detailed error message from deploy failure.

        Shows the TAIL of long output (the error is at the end, not the
        beginning). For Docker builds, also extracts the first few lines
        (which have the hop3 context) and the last lines (the actual error).
        """
        error_parts = [f"Exit code: {returncode}"]
        full_stdout = stdout.strip()

        if full_stdout:
            limit = 3000
            if len(full_stdout) <= limit:
                error_parts.append(f"stdout: {full_stdout}")
            else:
                # Show head (hop3 context) + tail (actual error)
                lines = full_stdout.split("\n")
                # First 5 lines for context, last lines for the error
                head = "\n".join(lines[:5])
                tail = full_stdout[-2000:]
                error_parts.append(
                    f"stdout (head): {head}\n"
                    f"... ({len(full_stdout)} chars total, showing last 2000) ...\n"
                    f"stdout (tail): {tail}"
                )

        if stderr:
            full_stderr = stderr.strip()
            if full_stderr:
                # Filter out cryptography warnings
                stderr_lines = [
                    line for line in full_stderr.split("\n")
                    if "CryptographyDeprecationWarning" not in line
                    and "TripleDES" not in line
                    and line.strip()
                ]
                if stderr_lines:
                    stderr_preview = "\n".join(stderr_lines)[-2000:]
                    error_parts.append(f"stderr: {stderr_preview}")

        return " | ".join(error_parts)

    def _deploy_via_cli(self) -> None:
        """Deploy via hop3 CLI subprocess.

        Always uses streaming output to show real-time progress and
        prevent silent hangs. Has a 10-minute timeout.

        Raises:
            DeploymentError: If deployment fails.
        """
        env = self._build_cli_env()
        cmd = ["hop3", "deploy", self.app_name, str(self._preparation.temp_dir)]

        verbose = self.config.get("verbose", False)
        debug = self.config.get("debug", False)

        # Key progress indicators that should always be shown
        _PROGRESS_PREFIXES = (">", "->", "!", "✓", "✗", "ERROR", "WARNING")

        def on_output(line: str):
            # Filter cryptography warnings
            if "CryptographyDeprecationWarning" in line or "TripleDES" in line:
                return
            if verbose or debug:
                self.console.info(f"  {line}")
            elif any(line.lstrip().startswith(p) for p in _PROGRESS_PREFIXES):
                # Always show key progress/error lines
                self.console.info(f"  {line}")
            else:
                self.console.debug(f"  {line}")

        # Always use streaming with timeout to prevent silent hangs
        result = run_streaming(cmd, on_output=on_output, env=env, timeout=600)
        stdout = result.stdout
        returncode = result.returncode

        if result.timed_out:
            self._last_deploy_error = "Deploy timed out after 10 minutes"
            self.console.error(self._last_deploy_error)
            raise DeploymentError(self._last_deploy_error)

        if returncode != 0:
            self._last_deploy_error = self._build_deploy_error_message(
                returncode, stdout
            )
            self.console.error(f"Deploy failed: {self._last_deploy_error}")
            raise DeploymentError(self._last_deploy_error)

        # Extract the app's direct port from deploy output.
        # The output contains: "port=XXXXX" in the DeploymentInfo line.
        self._extract_port_from_output(stdout)

    def _extract_port_from_output(self, stdout: str) -> None:
        """Extract the app's direct port from deploy output.

        Parses lines like:
            App running at: DeploymentInfo(protocol='http', address='127.0.0.1', port=55489)
        or:
            export PORT='55489'
        """
        import re  # noqa: PLC0415

        # Try DeploymentInfo pattern
        match = re.search(r"port=(\d+)", stdout)
        if match:
            self._app_port = int(match.group(1))
            self.console.debug(f"Extracted app port: {self._app_port}")
            return

        # Try export PORT pattern
        match = re.search(r"PORT='?(\d+)'?", stdout)
        if match:
            self._app_port = int(match.group(1))
            self.console.debug(f"Extracted app port from PORT: {self._app_port}")

    def check_deployed(self) -> bool:
        """Check if the app is deployed and running.

        Returns:
            True if app is deployed and running, False otherwise
        """
        self.last_check_output = ""

        if not self.deployed:
            self.last_check_output = "(not deployed)"
            return False

        try:
            env = self._build_cli_env()

            result = subprocess.run(
                ["hop3", "apps"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.last_check_output = (
                f"exit={result.returncode} "
                f"stdout={result.stdout[:500]} "
                f"stderr={result.stderr[:500]}"
            )

            app_in_list = self.app_name in result.stdout

            self.console.debug(f"check_deployed() for '{self.app_name}':")
            self.console.debug(f"  'hop3 apps' returned: {result.returncode}")
            self.console.debug(f"  stdout: {result.stdout[:500]}")
            if result.stderr:
                self.console.debug(f"  stderr: {result.stderr[:500]}")
            self.console.debug(f"  App in list: {app_in_list}")

            return app_in_list
        except Exception as e:
            self.last_check_output = f"exception: {e}"
            self.console.error(f"check_deployed() exception: {e}")
            traceback.print_exc()
            return False

    def get_app_port(self) -> int | None:
        """Get the app's direct HTTP port from deploy output.

        Parses the port from the deployment log which contains a line like:
        ``Deployment successful. App running at: DeploymentInfo(..., port=XXXXX)``

        Returns:
            The app's PORT number, or None if it can't be determined.
        """
        return self._app_port

    def test_http_detailed(
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int = HTTPStatus.OK,
        max_retries: int = 40,
    ) -> dict[str, Any]:
        """Test HTTP access and return detailed results.

        Prefers testing via the app's direct port (bypassing nginx) to
        avoid hostname resolution and SSL redirect issues in test
        environments. Falls back to nginx-based testing if the port
        can't be determined.

        Returns:
            Dict with: passed, message, details (url, status, body preview, etc.)
        """
        if not self.deployed:
            return {
                "passed": False,
                "message": "App not deployed yet",
                "details": {},
            }

        # Try to get the app's direct port and test without nginx
        app_port = self.get_app_port()
        if app_port:
            return self._test_http_direct(app_port, path, expected_status, max_retries)

        # No direct port (e.g., static apps served by nginx only).
        # For SSH targets, test via curl on the server with Host header.
        is_remote = self.target.info.ssh_host not in {"localhost", "127.0.0.1", None}
        if is_remote:
            return self._test_http_via_nginx_ssh(
                path, expected_status, max_retries,
            )

        # Fall back to local nginx-based testing
        verifier = self._get_verifier()
        return verifier.verify_http_detailed(
            hostname, path, expected_status, max_retries
        )

    def _test_http_direct(
        self,
        port: int,
        path: str,
        expected_status: int,
        max_retries: int,
    ) -> dict[str, Any]:
        """Test HTTP via the app's direct port, bypassing nginx.

        For Docker targets: connects from the test client to the container's
        internal IP (reachable via Docker network).

        For SSH targets: runs curl on the server itself (via SSH exec),
        because the app's direct port is typically blocked by the server
        firewall and not reachable from the test client.
        """
        url = f"http://127.0.0.1:{port}{path}"
        result: dict[str, Any] = {
            "passed": False,
            "message": "",
            "details": {"url": url, "direct_port": port},
        }

        self.console.info(f"Testing HTTP (direct port {port}): {path}")

        # Determine if we can connect directly or need to go via SSH
        is_docker = hasattr(self.target, "container_name") or (
            self.target.info.ssh_host not in {"localhost", "127.0.0.1"}
            and "192.168." in self.target.info.ssh_host
        )

        if is_docker:
            return self._test_http_local(
                self.target.info.ssh_host, port, path,
                expected_status, max_retries, result,
            )
        # SSH target: run curl on the server
        return self._test_http_via_ssh(
            port, path, expected_status, max_retries, result,
        )

    def _test_http_local(
        self,
        host: str,
        port: int,
        path: str,
        expected_status: int,
        max_retries: int,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Test HTTP by connecting directly from the test client."""
        import httpx  # noqa: PLC0415

        url = f"http://{host}:{port}{path}"
        result["details"]["url"] = url

        for attempt in range(max_retries):
            try:
                response = httpx.get(url, timeout=5.0, follow_redirects=True)
                result["details"]["status_code"] = response.status_code
                result["details"]["attempts"] = attempt + 1
                result["details"]["body_preview"] = (
                    response.text[:500] if response.text else ""
                )

                if response.status_code == expected_status:
                    result["passed"] = True
                    result["message"] = f"HTTP {response.status_code} from {url}"
                    self.console.success(
                        f"HTTP test passed (direct port {port}, status: {response.status_code})"
                    )
                    return result

                if response.status_code in {502, 503, 504}:
                    time.sleep(1)
                    continue

                result["message"] = (
                    f"HTTP {response.status_code} (expected {expected_status}) from {url}"
                )
                return result

            except (httpx.HTTPError, httpx.ConnectError) as e:
                result["details"]["last_error"] = str(e)
                self.console.debug(f"Attempt {attempt + 1}/{max_retries}: {e}")
                time.sleep(1)

        result["message"] = f"HTTP test failed after {max_retries} attempts on {url}"
        return result

    def _test_http_via_ssh(
        self,
        port: int,
        path: str,
        expected_status: int,
        max_retries: int,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Test HTTP by running curl on the remote server via SSH."""
        url = f"http://127.0.0.1:{port}{path}"
        result["details"]["url"] = url
        result["details"]["method"] = "ssh-curl"

        for attempt in range(max_retries):
            try:
                # exec_run returns (exit_code, stdout, stderr)
                _exit_code, stdout, _stderr = self.target.exec_run(
                    f"curl -s -o /dev/null -w '%{{http_code}}' "
                    f"--connect-timeout 3 --max-time 5 '{url}'"
                )
                status_str = stdout.strip() if stdout else ""

                if status_str.isdigit():
                    status_code = int(status_str)
                    result["details"]["status_code"] = status_code
                    result["details"]["attempts"] = attempt + 1

                    if status_code == expected_status:
                        # Fetch body for contains checks
                        _, body, _ = self.target.exec_run(
                            f"curl -s --max-time 3 '{url}' | head -c 500"
                        )
                        result["details"]["body_preview"] = (
                            body.strip() if body else ""
                        )
                        result["passed"] = True
                        result["message"] = f"HTTP {status_code} from {url}"
                        self.console.success(
                            f"HTTP test passed (direct port {port}, status: {status_code})"
                        )
                        return result

                    if status_code in {0, 502, 503, 504}:
                        time.sleep(1)
                        continue

                    # Get body preview for non-matching status
                    _, body, _ = self.target.exec_run(
                        f"curl -s --max-time 3 '{url}' | head -c 500"
                    )
                    body_text = body.strip() if body else ""
                    result["details"]["body_preview"] = body_text
                    body_hint = f"\n  Body: {body_text[:300]}" if body_text else ""
                    result["message"] = (
                        f"HTTP {status_code} (expected {expected_status}) "
                        f"from {url}{body_hint}"
                    )
                    return result

                # curl failed (connection refused, etc.) — app still starting
                time.sleep(1)

            except Exception as e:
                result["details"]["last_error"] = str(e)
                self.console.debug(f"Attempt {attempt + 1}/{max_retries}: {e}")
                time.sleep(1)

        result["message"] = f"HTTP test failed after {max_retries} attempts on {url}"
        return result

    def _test_http_via_nginx_ssh(
        self,
        path: str,
        expected_status: int,
        max_retries: int,
    ) -> dict[str, Any]:
        """Test HTTP via nginx on the remote server (for static/no-port apps).

        Runs curl on the server targeting localhost:80 with the app's
        hostname as Host header. Uses the app name as hostname since
        nginx is configured with HOST_NAME (or catch-all '_').
        """
        # Use the app name as hostname for the Host header
        host = self.app_name
        url = f"http://127.0.0.1{path}"
        result: dict[str, Any] = {
            "passed": False,
            "message": "",
            "details": {"url": url, "method": "nginx-ssh", "host": host},
        }

        self.console.info(f"Testing HTTP via nginx (Host: {host}): {path}")

        for attempt in range(max_retries):
            try:
                _exit_code, stdout, _stderr = self.target.exec_run(
                    f"curl -s -o /dev/null -w '%{{http_code}}' "
                    f"-H 'Host: {host}' "
                    f"--connect-timeout 3 --max-time 5 '{url}'"
                )
                status_str = stdout.strip() if stdout else ""

                if status_str.isdigit():
                    status_code = int(status_str)
                    result["details"]["status_code"] = status_code
                    result["details"]["attempts"] = attempt + 1

                    if status_code == expected_status:
                        # Fetch body for contains checks
                        _, body, _ = self.target.exec_run(
                            f"curl -s -H 'Host: {host}' --max-time 3 '{url}' | head -c 500"
                        )
                        result["details"]["body_preview"] = (
                            body.strip() if body else ""
                        )
                        result["passed"] = True
                        result["message"] = f"HTTP {status_code} from {url}"
                        self.console.success(
                            f"HTTP test passed (nginx, Host: {host}, status: {status_code})"
                        )
                        return result

                    if status_code in {0, 502, 503, 504}:
                        time.sleep(1)
                        continue

                    # Non-matching status — get body for diagnostics
                    _, body, _ = self.target.exec_run(
                        f"curl -s -H 'Host: {host}' --max-time 3 '{url}' | head -c 500"
                    )
                    body_text = body.strip() if body else ""
                    result["details"]["body_preview"] = body_text
                    body_hint = f"\n  Body: {body_text[:300]}" if body_text else ""
                    result["message"] = (
                        f"HTTP {status_code} (expected {expected_status}) "
                        f"from {url}{body_hint}"
                    )
                    return result

                time.sleep(1)

            except Exception as e:
                result["details"]["last_error"] = str(e)
                self.console.debug(f"Attempt {attempt + 1}/{max_retries}: {e}")
                time.sleep(1)

        result["message"] = f"HTTP test failed after {max_retries} attempts on {url}"
        return result

    def run_check_script_detailed(self) -> dict[str, Any]:
        """Run the app's check.py script and return detailed results.

        Returns:
            Dict with: passed, message, details
        """
        if not self.deployed:
            return {
                "passed": False,
                "message": "App not deployed yet",
                "details": {},
            }

        verifier = self._get_verifier()
        return verifier.run_check_script_detailed()

    def _get_verifier(self) -> AppVerifier:
        """Get a verifier instance for this session."""
        return AppVerifier(
            self.target.info,
            self.app,
            self.app_name,
            console=self.console,
        )

    def cleanup(self) -> None:
        """Cleanup the deployed app and temp files.

        Note: This method catches exceptions internally to ensure
        temp directory cleanup always happens.
        """
        # Destroy app on target
        if self.deployed:
            try:
                self._destroy_app()
            except CleanupError as e:
                self.console.warning(f"Cleanup warning: {e}")

        # Remove temp directory
        self._preparation.cleanup()

    def _destroy_app(self) -> None:
        """Destroy the deployed app on the target.

        Raises:
            CleanupError: If destruction fails.
        """
        try:
            env = self._build_cli_env()

            self.console.debug(f"Destroying {self.app_name}")

            # List apps before destroy (verbose only)
            if self.console.verbosity == Verbosity.VERBOSE:
                before = subprocess.run(
                    ["hop3", "apps"],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.console.debug(f"Apps before destroy:\n{before.stdout}")

            result = subprocess.run(
                ["hop3", "app:destroy", self.app_name, "-y"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                self.console.success(f"App {self.app_name} destroy command completed")
                if result.stdout.strip():
                    self.console.debug(f"[SERVER STDOUT] {result.stdout.strip()}")
                # Filter out cryptography warnings from stderr
                if result.stderr.strip():
                    stderr_lines = [
                        line
                        for line in result.stderr.split("\n")
                        if "CryptographyDeprecationWarning" not in line
                        and "TripleDES" not in line
                        and line.strip()
                    ]
                    if stderr_lines:
                        self.console.debug(f"[SERVER STDERR] {' '.join(stderr_lines)}")

                # Wait a moment for server-side cleanup
                time.sleep(2)

                # Verify app is gone
                self._verify_app_destroyed(env)
            else:
                self.console.error(
                    f"Failed to destroy app (exit code {result.returncode})"
                )
                error_msg = result.stderr[:200] if result.stderr else "Unknown error"
                self.deployed = False
                raise CleanupError(
                    f"Failed to destroy app '{self.app_name}': {error_msg}"
                )

            self.deployed = False

        except CleanupError:
            raise
        except Exception as e:
            self.console.error(f"Exception during destroy: {e}")
            traceback.print_exc()
            raise CleanupError(f"Exception during destroy: {e}") from e

    def _verify_app_destroyed(self, env: dict) -> None:
        """Verify the app was destroyed.

        Raises:
            CleanupError: If app is still present after destroy.
        """
        after = subprocess.run(
            ["hop3", "apps"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        if self.app_name in after.stdout:
            self.console.warning(f"{self.app_name} still in database after destroy!")
            raise CleanupError(
                f"App '{self.app_name}' still present in database after destroy"
            )

        self.console.info(f"Verified {self.app_name} removed from database")

    def __enter__(self) -> DeploymentSession:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit with cleanup."""
        self.cleanup()
