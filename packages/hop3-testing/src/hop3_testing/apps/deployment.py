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

from hop3_testing.targets.constants import E2E_TEST_SECRET_KEY
from hop3_testing.util.console import Console, PrintingConsole, Verbosity

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
            if session.test_http():
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

    def prepare(self):
        """Prepare the application for deployment.

        Creates a temporary copy of the app with git initialized.

        Returns:
            Path to the prepared app directory
        """
        return self._preparation.prepare()

    def deploy(self, wait_time: int = 5) -> bool:
        """Deploy the application to the target.

        Args:
            wait_time: Time to wait after deployment (seconds)

        Returns:
            True if deployment succeeded, False otherwise
        """
        if not self._preparation.temp_dir:
            self._preparation.prepare()

        self.console.status(f"Deploying {self.app_name}...")

        try:
            # Deploy via CLI (CLI will create tarball from directory)
            if not self._deploy_via_cli():
                return False

            self.deployed = True

            # Wait for deployment to complete
            self.console.info(f"Waiting {wait_time}s for deployment to complete...")
            time.sleep(wait_time)

            return True

        except Exception as e:
            self.console.error(f"Deployment failed: {e}")
            return False

    def _deploy_via_cli(self) -> bool:
        """Deploy via hop3 CLI subprocess.

        Returns:
            True if deployment succeeded, False otherwise
        """
        target_info = self.target.info

        env = os.environ.copy()
        env["HOP3_API_URL"] = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"
        env["HOP3_SSH_KEY"] = target_info.ssh_key or ""
        env["HOP3_SECRET_KEY"] = E2E_TEST_SECRET_KEY

        # Deploy from prepared temp directory
        # The CLI will create a tarball from this directory (excluding .git)
        result = subprocess.run(
            ["hop3", "deploy", self.app_name, str(self._preparation.temp_dir)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.console.debug(f"Deploy exit code: {result.returncode}")
        if result.stdout.strip():
            self.console.debug(f"Deploy stdout: {result.stdout.strip()}")

        # Filter cryptography warnings from stderr
        if result.stderr.strip():
            stderr_lines = [
                line
                for line in result.stderr.split("\n")
                if "CryptographyDeprecationWarning" not in line
                and "TripleDES" not in line
                and line.strip()
            ]
            if stderr_lines:
                self.console.debug(f"Deploy stderr: {' '.join(stderr_lines)}")

        if result.returncode != 0:
            self._last_deploy_error = result.stderr or "Deploy command failed"
            self.console.error(f"Deploy failed: {self._last_deploy_error}")
            return False

        return True

    def check_deployed(self) -> bool:
        """Check if the app is deployed and running.

        Returns:
            True if app is deployed and running, False otherwise
        """
        if not self.deployed:
            return False

        try:
            target_info = self.target.info

            env = os.environ.copy()
            env["HOP3_API_URL"] = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"
            env["HOP3_SSH_KEY"] = target_info.ssh_key or ""
            env["HOP3_SECRET_KEY"] = E2E_TEST_SECRET_KEY

            result = subprocess.run(
                ["hop3", "apps"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
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
            self.console.error(f"check_deployed() exception: {e}")
            traceback.print_exc()
            return False

    def test_http(
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int = HTTPStatus.OK,
        max_retries: int = 20,
    ) -> bool:
        """Test HTTP access to the deployed app.

        Args:
            hostname: Virtual host name (default: {app_name}.test.local)
            path: URL path to test
            expected_status: Expected HTTP status code
            max_retries: Maximum number of retry attempts

        Returns:
            True if test passed, False otherwise
        """
        if not self.deployed:
            self.console.warning("App not deployed yet")
            return False

        # Show debug info before testing if debug mode
        if self.config.get("debug", False):
            self._debugger.show_all()

        verifier = self._get_verifier()
        return verifier.verify_http(hostname, path, expected_status, max_retries)

    def test_http_detailed(
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int = HTTPStatus.OK,
        max_retries: int = 20,
    ) -> dict[str, Any]:
        """Test HTTP access and return detailed results.

        Returns:
            Dict with: passed, message, details (url, status, body preview, etc.)
        """
        if not self.deployed:
            return {
                "passed": False,
                "message": "App not deployed yet",
                "details": {},
            }

        verifier = self._get_verifier()
        return verifier.verify_http_detailed(
            hostname, path, expected_status, max_retries
        )

    def run_check_script(self) -> bool:
        """Run the app's check.py script if it exists.

        Returns:
            True if check passed, False otherwise
        """
        if not self.deployed:
            self.console.warning("App not deployed yet")
            return False

        verifier = self._get_verifier()
        return verifier.run_check_script()

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

    def cleanup(self) -> bool:
        """Cleanup the deployed app and temp files.

        Returns:
            True if cleanup succeeded, False otherwise
        """
        success = True

        # Destroy app on target
        if self.deployed:
            success = self._destroy_app()

        # Remove temp directory
        self._preparation.cleanup()

        return success

    def _destroy_app(self) -> bool:
        """Destroy the deployed app on the target."""
        success = True

        try:
            target_info = self.target.info

            env = os.environ.copy()
            env["HOP3_API_URL"] = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"
            env["HOP3_SSH_KEY"] = target_info.ssh_key or ""
            env["HOP3_SECRET_KEY"] = E2E_TEST_SECRET_KEY

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
                success = self._verify_app_destroyed(env)
            else:
                self.console.error(
                    f"Failed to destroy app (exit code {result.returncode})"
                )
                if result.stderr:
                    self.console.error(f"  Error: {result.stderr[:200]}")
                success = False

            self.deployed = False

        except Exception as e:
            self.console.error(f"Exception during destroy: {e}")
            traceback.print_exc()
            success = False

        return success

    def _verify_app_destroyed(self, env: dict) -> bool:
        """Verify the app was destroyed."""
        after = subprocess.run(
            ["hop3", "apps"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        if self.app_name in after.stdout:
            self.console.warning(f"{self.app_name} still in database after destroy!")
            return False

        self.console.info(f"Verified {self.app_name} removed from database")
        return True

    def run_full_test(self, cleanup: bool = True) -> bool:
        """Run a full test cycle: prepare, deploy, test, cleanup.

        Args:
            cleanup: Whether to cleanup after testing

        Returns:
            True if all tests passed, False otherwise
        """
        try:
            # Prepare
            self.console.start_phase(f"Preparing {self.app_name}")
            self.prepare()
            self.console.end_phase(f"Preparing {self.app_name}")

            # Deploy
            self.console.start_phase(f"Deploying {self.app_name}")
            if not self.deploy():
                self.console.end_phase(f"Deploying {self.app_name}", success=False)
                self.console.error(f"Deploy stage failed for {self.app_name}")
                return False
            self.console.end_phase(f"Deploying {self.app_name}")

            # Check deployment
            self.console.start_phase(f"Checking deployment for {self.app_name}")
            if not self.check_deployed():
                self.console.end_phase(
                    f"Checking deployment for {self.app_name}", success=False
                )
                self.console.error(f"Deployment check failed for {self.app_name}")
                return False
            self.console.end_phase(f"Checking deployment for {self.app_name}")

            # Test HTTP (if app has web interface)
            if self.app.has_procfile:
                self.console.start_phase(f"Testing HTTP for {self.app_name}")
                if not self.test_http():
                    self.console.end_phase(
                        f"Testing HTTP for {self.app_name}", success=False
                    )
                    self.console.error(f"HTTP test failed for {self.app_name}")
                    return False
                self.console.end_phase(f"Testing HTTP for {self.app_name}")

            # Run check script
            if self.app.has_check_script:
                self.console.start_phase(f"Running check script for {self.app_name}")
                if not self.run_check_script():
                    self.console.end_phase(
                        f"Running check script for {self.app_name}", success=False
                    )
                    self.console.error(f"Check script failed for {self.app_name}")
                    return False
                self.console.end_phase(f"Running check script for {self.app_name}")

            self.console.success(f"All tests passed for {self.app_name}")
            return True

        except Exception as e:
            self.console.error(f"Exception for {self.app_name}: {e}")
            traceback.print_exc()
            return False

        finally:
            if cleanup:
                self.console.start_phase(f"Cleanup for {self.app_name}")
                self.cleanup()
                self.console.end_phase(f"Cleanup for {self.app_name}")

    def __enter__(self) -> DeploymentSession:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit with cleanup."""
        self.cleanup()
