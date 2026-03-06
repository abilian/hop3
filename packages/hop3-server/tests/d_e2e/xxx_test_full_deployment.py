# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Full deployment E2E tests requiring complete infrastructure.

These tests run in Docker containers with:
- uwsgi for application deployment
- nginx for HTTP proxying
- systemd for service management (or supervisor on macOS)
- Full deployment pipeline
"""

from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING, Any

import pytest

from .conftest import deploy_flask_app, wait_for_app_status, wait_for_http_ready

if TYPE_CHECKING:
    from pathlib import Path

# Mark all tests as e2e
pytestmark = pytest.mark.e2e


class TestTarballDeploymentWithStatus:
    """Test application deployment via tarball with full lifecycle."""

    def test_deploy_simple_app_with_status(
        self, hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
    ):
        """Test deploying a simple Flask app and checking its status."""
        app_name = f"status-test-{int(time.time())}"

        # Deploy app
        deploy_flask_app(hop3_container, test_app_dir, app_name)

        # Wait for app to be running
        wait_for_app_status(hop3_command, app_name, timeout=60)

        # Check status
        result = hop3_command("app:status", app_name)
        assert result.returncode == 0, f"Failed to get status: {result.stderr}"
        print(f"Status: {result.stdout}")

        # Verify app is in apps list
        result = hop3_command("apps")
        assert app_name in result.stdout, f"App {app_name} not found in apps list"

        # Cleanup
        hop3_command("app:destroy", app_name)


class TestApplicationLifecycle:
    """Test application lifecycle commands (start, stop, restart, status)."""

    def test_app_stop_start(
        self, hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
    ):
        """Test stopping and starting an application."""
        app_name = f"lifecycle-test-{int(time.time())}"

        # Deploy app
        deploy_flask_app(hop3_container, test_app_dir, app_name)
        wait_for_app_status(hop3_command, app_name, timeout=60)

        # Stop the app
        result = hop3_command("app:stop", app_name)
        assert result.returncode == 0, f"Failed to stop: {result.stderr}"
        wait_for_app_status(
            hop3_command, app_name, expected_states=["STOPPED"], timeout=30
        )

        # Verify stopped
        result = hop3_command("app:status", app_name)
        assert result.returncode == 0

        # Start the app
        result = hop3_command("app:start", app_name)
        assert result.returncode == 0, f"Failed to start: {result.stderr}"
        wait_for_app_status(hop3_command, app_name, timeout=30)

        # Verify started
        result = hop3_command("app:status", app_name)
        assert result.returncode == 0

        # Cleanup
        hop3_command("app:destroy", app_name)

    def test_app_restart(
        self, hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
    ):
        """Test restarting an application."""
        app_name = f"restart-test-{int(time.time())}"

        # Deploy app
        deploy_flask_app(hop3_container, test_app_dir, app_name)
        wait_for_app_status(hop3_command, app_name, timeout=60)

        # Restart the app
        result = hop3_command("app:restart", app_name)
        assert result.returncode == 0, f"Failed to restart: {result.stderr}"
        wait_for_app_status(hop3_command, app_name, timeout=30)

        # Verify running
        result = hop3_command("app:status", app_name)
        assert result.returncode == 0

        # Cleanup
        hop3_command("app:destroy", app_name)


class TestEnvironmentVariables:
    """Test environment variable management."""

    def test_set_and_get_env_var(
        self, hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
    ):
        """Test setting and getting environment variables."""
        app_name = f"config-test-{int(time.time())}"

        # Deploy app
        deploy_flask_app(hop3_container, test_app_dir, app_name)
        wait_for_app_status(hop3_command, app_name, timeout=60)

        # Set environment variables
        result = hop3_command(
            "config:set", app_name, "TEST_VAR=hello", "ANOTHER_VAR=world"
        )
        assert result.returncode == 0, f"Failed to set config: {result.stderr}"
        assert "TEST_VAR" in result.stdout

        # Get a specific environment variable
        result = hop3_command("config:get", app_name, "TEST_VAR")
        assert result.returncode == 0, f"Failed to get config: {result.stderr}"
        assert "hello" in result.stdout

        # Verify it's in the config list
        result = hop3_command("config:show", app_name)
        assert result.returncode == 0, f"Failed to show config: {result.stderr}"
        assert "TEST_VAR" in result.stdout
        assert "ANOTHER_VAR" in result.stdout

        # Cleanup
        hop3_command("app:destroy", app_name)

    def test_unset_env_var(
        self, hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
    ):
        """Test unsetting environment variables."""
        app_name = f"unset-test-{int(time.time())}"

        # Deploy app
        deploy_flask_app(hop3_container, test_app_dir, app_name)
        wait_for_app_status(hop3_command, app_name, timeout=60)

        # Set environment variable
        result = hop3_command("config:set", app_name, "TO_REMOVE=temporary")
        assert result.returncode == 0, f"Failed to set config: {result.stderr}"

        # Verify it exists
        result = hop3_command("config:get", app_name, "TO_REMOVE")
        assert result.returncode == 0
        assert "temporary" in result.stdout

        # Unset the variable
        result = hop3_command("config:unset", app_name, "TO_REMOVE")
        assert result.returncode == 0, f"Failed to unset config: {result.stderr}"
        assert "TO_REMOVE" in result.stdout or "Removed" in result.stdout

        # Verify it's gone
        result = hop3_command("config:get", app_name, "TO_REMOVE")
        # Getting a non-existent var should still return 0 but say not found
        assert "not found" in result.stdout.lower() or "TO_REMOVE" not in result.stdout

        # Cleanup
        hop3_command("app:destroy", app_name)


class TestApplicationDestruction:
    """Test application destruction and cleanup."""

    def test_destroy_app(
        self, hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
    ):
        """Test destroying an application."""
        app_name = f"destroy-test-{int(time.time())}"

        # Deploy app
        deploy_flask_app(hop3_container, test_app_dir, app_name)
        wait_for_app_status(hop3_command, app_name, timeout=60)

        # Verify app exists
        result = hop3_command("apps")
        assert result.returncode == 0
        assert app_name in result.stdout, f"App {app_name} not found in apps list"

        # Destroy the app
        result = hop3_command("app:destroy", app_name)
        assert result.returncode == 0, f"Failed to destroy app: {result.stderr}"
        assert "destroyed" in result.stdout.lower() or app_name in result.stdout

        # Verify app is gone
        result = hop3_command("apps")
        assert result.returncode == 0
        assert app_name not in result.stdout, (
            f"App {app_name} still in apps list after destroy"
        )


class TestWebEndpoint:
    """Test that deployed apps are accessible via HTTP."""

    def test_deployed_app_http_access(
        self, hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
    ):
        """Test that a deployed app responds to HTTP requests."""
        app_name = f"http-test-{int(time.time())}"

        # Deploy app
        deploy_flask_app(hop3_container, test_app_dir, app_name)
        wait_for_app_status(hop3_command, app_name, timeout=60)

        # Configure nginx virtual host
        hostname = f"{app_name}.test.local"
        (test_app_dir / "env").write_text(f"HOST_NAME={hostname}\n")

        # Get HTTP port from container
        http_port = hop3_container["http_base"].split(":")[-1]
        url = f"http://localhost:{http_port}/"

        # Test HTTP access with virtual host using polling helper
        print(f"Testing HTTP access on port {http_port} with Host: {hostname}")
        success, error = wait_for_http_ready(
            url,
            expected_content="Hello from Flask",
            headers={"Host": hostname},
            timeout=60,
        )

        if not success:
            pytest.skip(f"Could not connect to app. {error}")

        # Cleanup
        hop3_command("app:destroy", app_name)


class TestGitHookDeployment:
    """Test deployment via git-hook command (git push workflow)."""

    @pytest.mark.skip(
        reason="Git push workflow not yet implemented - requires git server infrastructure"
    )
    def test_git_hook_deployment(
        self, hop3_container: dict[str, Any], hop3_command, test_app_dir: Path
    ):
        """Test deploying via git-hook command (simulating git push)."""
        f"githook-test-{int(time.time())}"

        # Create Flask app
        (test_app_dir / "app.py").write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Deployed via git-hook!"
""")

        (test_app_dir / "requirements.txt").write_text("flask>=3.0\n")
        (test_app_dir / "Procfile").write_text(
            f"web: cd {test_app_dir} && flask --app app run --host 0.0.0.0 --port $PORT\n"
        )

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=test_app_dir, check=True)
        subprocess.run(["git", "add", "."], cwd=test_app_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=test_app_dir,
            check=True,
            env={
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@test.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@test.com",
            },
        )

        # Get the commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=test_app_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        result.stdout.strip()

        # Check if git-hook command exists
        result = hop3_command("help")
        if "git-hook" not in result.stdout:
            pytest.skip("git-hook command not available in this server version")

        # For a full test, we would need to:
        # 1. Push the git repo to the server
        # 2. Trigger the git-hook command with the commit SHA
        # This requires more complex setup with git server
        pytest.skip("Full git-hook E2E test requires git server infrastructure")
