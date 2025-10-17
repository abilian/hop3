# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deployment session for test applications."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import time
import traceback
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from hop3_cli.client import Client
from hop3_cli.config import Config

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget

    from .catalog import TestApp


class DeploymentSession:
    """Manages the deployment and testing of a test application.

    This class handles:
    - Preparing the app for deployment (git init, creating tarball)
    - Deploying to the target via hop3 CLI
    - Testing the deployed app
    - Cleanup
    """

    def __init__(
        self,
        app: TestApp,
        target: DeploymentTarget,
        app_name: str | None = None,
        config: dict[str, Any] | None = None,
    ):
        """Initialize deployment session.

        Args:
            app: Test application to deploy
            target: Deployment target
            app_name: Name for the deployed app (default: auto-generated)
            config: Additional configuration (debug, verbose, etc.)
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
        self.temp_dir: Path | None = None

        # Debug settings
        self.verbose = self.config.get("verbose", False)
        self.debug = self.config.get("debug", False)

    def prepare(self) -> Path:
        """Prepare the application for deployment.

        Creates a temporary copy of the app with git initialized.

        Returns:
            Path to the prepared app directory
        """
        # Create temp directory
        self.temp_dir = Path("/tmp") / f"hop3-test-{self.app_name}"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

        # Copy app to temp directory
        shutil.copytree(self.app.path, self.temp_dir)

        # Create ENV file with nginx configuration if not present
        # This must happen before git commit so it's included in the tarball
        env_file = self.temp_dir / "ENV"
        if not env_file.exists() and self.app.has_procfile:
            hostname = f"{self.app_name}.test.local"
            env_file.write_text(f"HOST_NAME={hostname}\n")

        # Initialize git if not already initialized
        git_dir = self.temp_dir / ".git"
        if not git_dir.exists():
            subprocess.run(
                ["git", "init"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "add", "."],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

        return self.temp_dir

    def deploy(self, wait_time: int = 15) -> bool:
        """Deploy the application to the target.

        Args:
            wait_time: Time to wait after deployment (seconds)

        Returns:
            True if deployment succeeded, False otherwise
        """
        if not self.temp_dir:
            self.prepare()

        print(f"\nDeploying {self.app_name}...")

        try:
            # Create tarball
            tarball_path = Path("/tmp") / f"{self.app_name}.tar.gz"
            subprocess.run(
                ["git", "archive", "--format=tar.gz", "-o", str(tarball_path), "HEAD"],
                cwd=self.temp_dir,
                check=True,
                capture_output=True,
            )

            # Read and encode tarball
            tarball_bytes = tarball_path.read_bytes()
            repository_b64 = base64.b64encode(tarball_bytes).decode("utf-8")

            # Deploy via RPC
            target_info = self.target.info

            # Build SSH API URL (must use api_url_override to bypass HOP3_API_URL env var)
            api_url = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"

            env_config = {
                "ssh_key": target_info.ssh_key,
            }

            config = Config(data=env_config)
            client = Client(config=config, state=None, api_url_override=api_url)

            try:
                response = client.rpc(
                    "cli", ["deploy", self.app_name], repository=repository_b64
                )
                print(f"Deploy response: {response}")
            finally:
                # Close tunnel to prevent hanging
                if client.tunnel:
                    client.tunnel.stop()
                    client.tunnel = None

            self.deployed = True

            # Wait for deployment to complete
            print(f"Waiting {wait_time}s for deployment to complete...")
            time.sleep(wait_time)

            # Cleanup tarball
            tarball_path.unlink(missing_ok=True)

            return True

        except Exception as e:
            print(f"Deployment failed: {e}")
            return False

    def check_deployed(self) -> bool:
        """Check if the app is deployed and running.

        Returns:
            True if app is deployed and running, False otherwise
        """
        if not self.deployed:
            return False

        try:
            # Use hop3 CLI to check status
            target_info = self.target.info

            env = os.environ.copy()
            env["HOP3_API_URL"] = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"
            env["HOP3_SSH_KEY"] = target_info.ssh_key or ""
            env["HOP3_SECRET_KEY"] = "e2e-test-secret-key-do-not-use-in-production"

            result = subprocess.run(
                ["hop3", "apps"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            print(f"check_deployed() for '{self.app_name}':")
            print(f"  'hop3 apps' returned: {result.returncode}")
            print(f"  stdout: {result.stdout[:500]}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")
            print(f"  App in list: {self.app_name in result.stdout}")

            return self.app_name in result.stdout
        except Exception as e:
            print(f"check_deployed() exception: {e}")
            traceback.print_exc()
            return False

    def test_http(
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int = HTTPStatus.OK,
        max_retries: int = 30,
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
            print("App not deployed yet")
            return False

        if hostname is None:
            hostname = f"{self.app_name}.test.local"

        target_info = self.target.info
        http_port = target_info.http_base.split(":")[-1]
        url = f"http://localhost:{http_port}{path}"

        print(f"\nTesting HTTP: {url} (Host: {hostname})")

        # If debug mode, show nginx config and logs before testing
        if self.debug:
            self._debug_nginx_config()
            self._debug_app_logs()

        for attempt in range(max_retries):
            try:
                response = httpx.get(
                    url,
                    headers={"Host": hostname},
                    timeout=2.0,
                    follow_redirects=True,
                )

                if response.status_code == expected_status:
                    print(f"✓ HTTP test passed (status: {response.status_code})")
                    return True

                if response.status_code == HTTPStatus.BAD_GATEWAY:
                    # Backend not ready, retry
                    print(f"  Attempt {attempt + 1}/{max_retries}: Backend not ready, retrying...")
                    time.sleep(1)
                    continue

                print(f"  Unexpected status code: {response.status_code}")
                return False

            except (httpx.HTTPError, httpx.ConnectError) as e:
                print(f"  Attempt {attempt + 1}/{max_retries}: {e}")
                time.sleep(1)

        print(f"✗ HTTP test failed after {max_retries} attempts")
        return False

    def run_check_script(self) -> bool:
        """Run the app's check.py script if it exists.

        Returns:
            True if check passed, False otherwise
        """
        if not self.app.has_check_script:
            print("No check script available")
            return True

        if not self.deployed:
            print("App not deployed yet")
            return False

        try:
            hostname = f"{self.app_name}.test.local"
            target_info = self.target.info
            http_port = int(target_info.http_base.split(":")[-1])

            check_script_path = self.app.path / "check.py"

            # Execute check script
            ctx: dict[str, Any] = {}
            exec(check_script_path.read_text(), ctx)

            if "check" not in ctx:
                print("check() function not found in check.py")
                return False

            # Pass both hostname and port to check script
            # Check scripts use assertions - if they complete without error, they passed
            ctx["check"](hostname, http_port)
            print("✓ Check script passed")
            return True

        except Exception as e:
            print(f"✗ Check script failed: {e}")
            return False

    def cleanup(self) -> bool:
        """Cleanup the deployed app and temp files.

        Returns:
            True if cleanup succeeded, False otherwise
        """
        success = True

        # Destroy app on target
        if self.deployed:
            try:
                target_info = self.target.info

                env = os.environ.copy()
                env["HOP3_API_URL"] = f"ssh://{target_info.ssh_host}:{target_info.ssh_port}"
                env["HOP3_SSH_KEY"] = target_info.ssh_key or ""
                env["HOP3_SECRET_KEY"] = "e2e-test-secret-key-do-not-use-in-production"

                print(f"\n[DEBUG] Destroying {self.app_name}")

                # List apps before destroy
                before = subprocess.run(
                    ["hop3", "apps"],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                print(f"[DEBUG] Apps before destroy:\n{before.stdout}")

                result = subprocess.run(
                    ["hop3", "app:destroy", self.app_name],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode == 0:
                    print(f"✓ App {self.app_name} destroy command completed")
                    print(f"[SERVER STDOUT] (length={len(result.stdout)})")
                    if result.stdout.strip():
                        print(result.stdout)
                    print(f"[SERVER STDERR] (length={len(result.stderr)})")
                    if result.stderr.strip():
                        # Filter out cryptography warnings
                        stderr_lines = [l for l in result.stderr.split('\n') if 'CryptographyDeprecationWarning' not in l and 'TripleDES' not in l]
                        if stderr_lines:
                            print('\n'.join(stderr_lines))

                    # Wait a moment for server-side cleanup
                    time.sleep(2)

                    # Check if app is gone
                    after = subprocess.run(
                        ["hop3", "apps"],
                        env=env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    print(f"[DEBUG] Apps after destroy:\n{after.stdout}")

                    if self.app_name in after.stdout:
                        print(f"⚠ WARNING: {self.app_name} still in database after destroy!")
                        success = False
                    else:
                        print(f"✓ Verified {self.app_name} removed from database")
                else:
                    print(f"❌ Failed to destroy app (exit code {result.returncode})")
                    if result.stderr:
                        print(f"[DEBUG] Destroy stderr: {result.stderr}")
                    success = False

                self.deployed = False

            except Exception as e:
                print(f"❌ Exception during destroy: {e}")
                traceback.print_exc()
                success = False

        # Remove temp directory
        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                print(f"✓ Temp directory removed")
            except Exception as e:
                print(f"⚠ Error removing temp directory: {e}")
                success = False

        return success

    def run_full_test(self, cleanup: bool = True) -> bool:
        """Run a full test cycle: prepare, deploy, test, cleanup.

        Args:
            cleanup: Whether to cleanup after testing

        Returns:
            True if all tests passed, False otherwise
        """
        try:
            # Prepare
            print(f"[STAGE] Preparing {self.app_name}")
            self.prepare()

            # Deploy
            print(f"[STAGE] Deploying {self.app_name}")
            if not self.deploy():
                print(f"❌ [FAILED AT] Deploy stage for {self.app_name}")
                return False

            # Check deployment
            print(f"[STAGE] Checking deployment for {self.app_name}")
            if not self.check_deployed():
                print(f"❌ [FAILED AT] Deployment check for {self.app_name}")
                return False

            # Test HTTP (if app has web interface)
            if self.app.has_procfile:
                print(f"[STAGE] Testing HTTP for {self.app_name}")
                if not self.test_http():
                    print(f"❌ [FAILED AT] HTTP test for {self.app_name}")
                    return False

            # Run check script
            if self.app.has_check_script:
                print(f"[STAGE] Running check script for {self.app_name}")
                if not self.run_check_script():
                    print(f"❌ [FAILED AT] Check script for {self.app_name}")
                    return False

            print(f"✓ All tests passed for {self.app_name}")
            return True

        except Exception as e:
            print(f"❌ [FAILED AT] Exception for {self.app_name}: {e}")
            traceback.print_exc()
            return False

        finally:
            if cleanup:
                print(f"[STAGE] Cleanup for {self.app_name}")
                self.cleanup()

    def __enter__(self) -> DeploymentSession:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit with cleanup."""
        self.cleanup()

    def _debug_nginx_config(self) -> None:
        """Debug helper: print nginx configuration for the app."""
        print("\n" + "=" * 70)
        print(f"DEBUG: Nginx config for {self.app_name}")
        print("=" * 70)

        try:
            # Check if nginx config exists
            exit_code, stdout, stderr = self.target.exec_run(
                f"test -f /home/hop3/nginx/{self.app_name}.conf && echo 'exists' || echo 'missing'"
            )

            if "exists" in stdout:
                print(f"✓ Nginx config found at /home/hop3/nginx/{self.app_name}.conf")

                # Show config content
                exit_code, stdout, stderr = self.target.exec_run(
                    f"cat /home/hop3/nginx/{self.app_name}.conf"
                )
                print("\nConfig content:")
                print(stdout)
            else:
                print(f"✗ Nginx config NOT found at /home/hop3/nginx/{self.app_name}.conf")

            # Check nginx status
            print("\nNginx status:")
            exit_code, stdout, stderr = self.target.exec_run(
                "systemctl is-active nginx 2>/dev/null || service nginx status 2>/dev/null || echo 'unknown'"
            )
            print(stdout)

            # Check nginx error logs
            print("\nNginx error log (last 20 lines):")
            exit_code, stdout, stderr = self.target.exec_run(
                "tail -n 20 /var/log/nginx/error.log 2>/dev/null || echo 'No error log'"
            )
            print(stdout)

        except Exception as e:
            print(f"Error getting nginx debug info: {e}")

        print("=" * 70 + "\n")

    def _debug_app_logs(self) -> None:
        """Debug helper: print app logs."""
        print("\n" + "=" * 70)
        print(f"DEBUG: App logs for {self.app_name}")
        print("=" * 70)

        try:
            # Check app directory structure
            exit_code, stdout, stderr = self.target.exec_run(
                f"ls -la /home/hop3/apps/{self.app_name}/ 2>/dev/null || echo 'App directory not found'"
            )
            print("App directory structure:")
            print(stdout)

            # Check if src exists
            exit_code, stdout, stderr = self.target.exec_run(
                f"ls -la /home/hop3/apps/{self.app_name}/src/ 2>/dev/null || echo 'Src directory not found'"
            )
            print("\nSrc directory:")
            print(stdout)

            # Check logs directory
            exit_code, stdout, stderr = self.target.exec_run(
                f"ls -la /home/hop3/apps/{self.app_name}/log/ 2>/dev/null || echo 'Log directory not found'"
            )
            print("\nLog directory:")
            print(stdout)

            # Show any log files
            exit_code, stdout, stderr = self.target.exec_run(
                f"find /home/hop3/apps/{self.app_name}/log -type f -exec tail -n 10 {{}} \\; 2>/dev/null || echo 'No log files'"
            )
            if stdout.strip():
                print("\nLog contents:")
                print(stdout)

        except Exception as e:
            print(f"Error getting app debug info: {e}")

        print("=" * 70 + "\n")
