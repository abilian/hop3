# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""E2E tests for hop3-deploy tool.

These tests verify that hop3-deploy correctly deploys hop3-server
to Docker containers and remote servers.
"""

from __future__ import annotations

import subprocess

import pytest

# Container name used by hop3-deploy
DEPLOY_CONTAINER = "hop3-dev"


@pytest.mark.e2e
@pytest.mark.slow
class TestDeployer:
    """Test hop3-deploy functionality."""

    @pytest.fixture(autouse=True)
    def cleanup_container(self):
        """Clean up Docker container before and after test."""
        # Cleanup before
        subprocess.run(
            ["docker", "rm", "-f", DEPLOY_CONTAINER],
            capture_output=True,
            check=False,
        )

        yield

        # Cleanup after
        subprocess.run(
            ["docker", "rm", "-f", DEPLOY_CONTAINER],
            capture_output=True,
            check=False,
        )

    def test_deploy_to_docker_with_local_code(self) -> None:
        """Test hop3-deploy --docker --local deploys successfully.

        This tests the development workflow where local code is uploaded
        and installed on a Docker container.
        """
        # Check hop3-deploy command exists
        result = subprocess.run(
            ["which", "hop3-deploy"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("hop3-deploy command not found in PATH")

        # Run hop3-deploy
        result = subprocess.run(
            ["hop3-deploy", "--docker", "--local"],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes max
            check=False,
        )

        # Check deployment succeeded
        assert result.returncode == 0, (
            f"hop3-deploy failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Verify container is running
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={DEPLOY_CONTAINER}", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.stdout.strip(), "Container not running after deploy"

        # Verify hop3-server is installed in container
        result = subprocess.run(
            [
                "docker",
                "exec",
                DEPLOY_CONTAINER,
                "test",
                "-f",
                "/home/hop3/venv/bin/hop3-server",
            ],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, "hop3-server not installed in container"

        # Note: Full HTTP server tests require systemd which is not available
        # in basic Docker containers. The deployment test above verifies:
        # 1. hop3-deploy runs without errors
        # 2. Container is created and running
        # 3. hop3-server binary is installed in the correct location
        #
        # For full integration testing with HTTP endpoints, use hop3-testing
        # which has systemd-enabled containers.


@pytest.mark.e2e
class TestDeployerHelp:
    """Test hop3-deploy help and basic functionality."""

    def test_deploy_help(self) -> None:
        """Test hop3-deploy --help works."""
        result = subprocess.run(
            ["hop3-deploy", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Should succeed or at least not crash
        assert result.returncode == 0, f"hop3-deploy --help failed: {result.stderr}"
        assert "hop3" in result.stdout.lower() or "deploy" in result.stdout.lower()

    def test_deploy_requires_target(self) -> None:
        """Test hop3-deploy without --docker or --host fails gracefully."""
        result = subprocess.run(
            ["hop3-deploy"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Should fail but with a helpful message
        assert result.returncode != 0
        # Should mention needing a target
        output = (result.stdout + result.stderr).lower()
        assert "docker" in output or "host" in output or "target" in output
