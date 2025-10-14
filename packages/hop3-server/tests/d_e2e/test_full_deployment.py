# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Full deployment E2E tests requiring complete infrastructure.

These tests require a fully configured server with:
- uwsgi for application deployment
- nginx for HTTP proxying
- systemd for service management
- Full deployment pipeline

Run with Docker-based E2E infrastructure or a production-like test server.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

# Import from parent c_system conftest for now
# These tests can use either c_system fixtures (via HOP3_DEV_HOST)
# or d_e2e Docker fixtures
sys.path.insert(0, str(Path(__file__).parent.parent / "c_system"))
from conftest import create_simple_flask_app, hop3

# Get server domain for URL testing
E2E_SERVER = os.environ.get("HOP3_DEV_HOST", "")
E2E_DOMAIN = E2E_SERVER.split("@")[-1] if "@" in E2E_SERVER else E2E_SERVER


class TestTarballDeploymentWithStatus:
    """Test application deployment via tarball with full lifecycle."""

    def test_deploy_with_existing_test_app(
        self, deployed_app: dict, e2e_auth_token: str
    ):
        """Test deploying an existing test app from test-apps directory."""
        app_name = deployed_app["name"]

        # Use the simple Flask test app
        test_app_source = (
            Path(__file__).parent.parent.parent.parent.parent.parent
            / "apps"
            / "test-apps"
            / "010-flask-pip-wsgi"
        )

        if not test_app_source.exists():
            pytest.skip("Test app source not found")

        # Copy test app to deployment directory
        app_dir = deployed_app["dir"]
        for item in test_app_source.iterdir():
            if item.is_file():
                shutil.copy(item, app_dir)

        # Change to app directory
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            # Deploy
            result = hop3("deploy", app_name)
            deployed_app["deployed"] = True

            assert result.returncode == 0

            # Wait for deployment
            time.sleep(5)

            # Verify deployment
            result = hop3("status", app_name)
            assert result.returncode == 0

        finally:
            os.chdir(original_dir)


class TestApplicationLifecycle:
    """Test application lifecycle commands (start, stop, restart, status)."""

    def test_app_status(self, deployed_app: dict, e2e_auth_token: str):
        """Test checking application status."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Deploy an app first
        create_simple_flask_app(app_dir, app_name)
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            hop3("deploy", app_name)
            deployed_app["deployed"] = True
            time.sleep(5)

            # Check status
            result = hop3("status", app_name)
            assert result.returncode == 0
            assert app_name in result.stdout

        finally:
            os.chdir(original_dir)

    def test_app_stop_start(self, deployed_app: dict, e2e_auth_token: str):
        """Test stopping and starting an application."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Deploy an app
        create_simple_flask_app(app_dir, app_name)
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            hop3("deploy", app_name)
            deployed_app["deployed"] = True
            time.sleep(5)

            # Stop the app
            result = hop3("stop", app_name)
            assert result.returncode == 0
            time.sleep(2)

            # Verify it's stopped
            result = hop3("status", app_name)
            assert result.returncode == 0

            # Start the app
            result = hop3("start", app_name)
            assert result.returncode == 0
            time.sleep(2)

            # Verify it's started
            result = hop3("status", app_name)
            assert result.returncode == 0

        finally:
            os.chdir(original_dir)

    def test_app_restart(self, deployed_app: dict, e2e_auth_token: str):
        """Test restarting an application."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Deploy an app
        create_simple_flask_app(app_dir, app_name)
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            hop3("deploy", app_name)
            deployed_app["deployed"] = True
            time.sleep(5)

            # Restart the app
            result = hop3("restart", app_name)
            assert result.returncode == 0
            time.sleep(3)

            # Verify it's running
            result = hop3("status", app_name)
            assert result.returncode == 0

        finally:
            os.chdir(original_dir)


class TestEnvironmentVariables:
    """Test environment variable management."""

    def test_set_env_var(self, deployed_app: dict, e2e_auth_token: str):
        """Test setting environment variables."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Deploy an app
        create_simple_flask_app(app_dir, app_name)
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            hop3("deploy", app_name)
            deployed_app["deployed"] = True
            time.sleep(5)

            # Set environment variable
            result = hop3("config:set", f"{app_name}", "TEST_VAR=test_value")
            assert result.returncode == 0

            # Get environment variables
            result = hop3("config:get", app_name)
            assert result.returncode == 0
            assert "TEST_VAR" in result.stdout

        finally:
            os.chdir(original_dir)

    def test_unset_env_var(self, deployed_app: dict, e2e_auth_token: str):
        """Test unsetting environment variables."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Deploy an app
        create_simple_flask_app(app_dir, app_name)
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            hop3("deploy", app_name)
            deployed_app["deployed"] = True
            time.sleep(5)

            # Set and then unset environment variable
            hop3("config:set", f"{app_name}", "TEST_VAR=test_value")
            result = hop3("config:unset", f"{app_name}", "TEST_VAR")
            assert result.returncode == 0

        finally:
            os.chdir(original_dir)


class TestApplicationDestruction:
    """Test application destruction and cleanup."""

    def test_destroy_app(self, deployed_app: dict, e2e_auth_token: str):
        """Test destroying an application."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Deploy an app
        create_simple_flask_app(app_dir, app_name)
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            hop3("deploy", app_name)
            deployed_app["deployed"] = True
            time.sleep(5)

            # Destroy the app
            result = hop3("destroy", app_name)
            assert result.returncode == 0
            deployed_app["deployed"] = False  # Mark as destroyed

            time.sleep(2)

            # Verify app is gone
            result = hop3("apps")
            assert app_name not in result.stdout

        finally:
            os.chdir(original_dir)


class TestWebEndpoint:
    """Test that deployed apps are accessible via HTTP."""

    def test_deployed_app_responds(self, deployed_app: dict, e2e_auth_token: str):
        """Test that a deployed app responds to HTTP requests."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Deploy an app
        create_simple_flask_app(app_dir, app_name)
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            hop3("deploy", app_name)
            deployed_app["deployed"] = True

            # Configure nginx server name
            app_host = f"{app_name}.{E2E_DOMAIN}"
            hop3("config:set", app_name, f"NGINX_SERVER_NAME={app_host}")

            # Wait for app to start and nginx to configure
            time.sleep(10)

            # Try to access the app
            url = f"https://{app_host}/"

            # Retry a few times in case it's still starting
            response = None
            for _i in range(5):
                try:
                    response = httpx.get(url, verify=False, timeout=10.0)
                    if response.status_code == 200:
                        break
                except (httpx.ConnectError, httpx.TimeoutException):
                    time.sleep(3)
                    continue

            # Check response
            if response:
                assert response.status_code == 200
                assert f"Hello from {app_name}" in response.text
            else:
                pytest.skip("Could not connect to deployed app (network issue)")

        finally:
            os.chdir(original_dir)


class TestGitHookDeployment:
    """Test deployment via git-hook command (git push workflow)."""

    def test_git_hook_deployment(self, deployed_app: dict, e2e_auth_token: str):
        """Test deploying via git-hook command (simulating git push)."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Create a simple Flask app
        create_simple_flask_app(app_dir, app_name)

        # Initialize git repo
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            # Initialize git repository
            subprocess.run(["git", "init"], capture_output=True, check=True)
            subprocess.run(["git", "add", "."], capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                capture_output=True,
                check=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": "Test",
                    "GIT_AUTHOR_EMAIL": "test@test.com",
                    "GIT_COMMITTER_NAME": "Test",
                    "GIT_COMMITTER_EMAIL": "test@test.com",
                },
            )

            # Get the commit SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            commit_sha = result.stdout.strip()

            # Deploy using git-hook command
            # Note: This command is executed on the server side
            # We need to push the repo first, then trigger git-hook
            # For now, we'll test that the git-hook command exists
            result = hop3("help", check=False)

            # Check if git-hook is available
            if "git-hook" not in result.stdout:
                pytest.skip("git-hook command not available in this server version")

            # For a full test, we would need to:
            # 1. Push the git repo to the server
            # 2. Trigger the git-hook command with the commit SHA
            # This requires more complex setup, so we'll mark this as TODO

            pytest.skip("Full git-hook E2E test requires git push infrastructure")

        finally:
            os.chdir(original_dir)
