# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""E2E tests for hop3-deploy tool.

These tests verify that hop3-deploy correctly deploys hop3-server
to Docker containers and remote servers.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from .utils.backends import ssh_host_available, ssh_raw_host

# Container name used by hop3-deploy
DEPLOY_CONTAINER = "hop3-dev"


@pytest.mark.e2e
@pytest.mark.slow
class TestDeployer:
    """Test hop3-deploy functionality."""

    @pytest.fixture(autouse=True)
    def check_deploy_command(self):
        """Skip if hop3-deploy is not available."""
        result = subprocess.run(
            ["which", "hop3-deploy-server"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("hop3-deploy command not found in PATH")

    @pytest.fixture(autouse=True)
    def cleanup_docker(self):
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

    def test_deploy_with_local_code(self, deploy_target: str) -> None:
        """Test hop3-deploy with local code deploys successfully.

        This tests the development workflow where local code is uploaded
        and installed on the target (Docker or SSH).

        The deploy_target fixture is dynamically parametrized based on CLI options.
        """
        if deploy_target == "docker":
            deploy_args = ["hop3-deploy-server", "--docker", "--local"]
        else:  # ssh
            host = ssh_raw_host()
            deploy_args = ["hop3-deploy-server", "--host", host, "--local", "--clean"]

        # Run hop3-deploy
        result = subprocess.run(  # ty: ignore[no-matching-overload]
            deploy_args,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes max
            check=False,
            env={**os.environ, "HOP3_NONINTERACTIVE": "1"},
        )

        # Check deployment succeeded
        assert result.returncode == 0, (
            f"hop3-deploy failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Verify installation based on target
        if deploy_target == "docker":
            self._verify_docker_deployment()
        else:
            self._verify_ssh_deployment()

    def _verify_docker_deployment(self) -> None:
        """Verify deployment to Docker container."""
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

    def _verify_ssh_deployment(self) -> None:
        """Verify deployment to SSH host."""
        host = ssh_host_available()

        # Verify hop3-server is installed on remote host
        result = subprocess.run(  # ty: ignore[no-matching-overload]
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                host,
                "test -f /home/hop3/venv/bin/hop3-server",
            ],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, "hop3-server not installed on remote host"


@pytest.mark.e2e
class TestDeployerHelp:
    """Test hop3-deploy help and basic functionality."""

    def test_deploy_help(self) -> None:
        """Test hop3-deploy --help works."""
        result = subprocess.run(
            ["hop3-deploy-server", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Should succeed or at least not crash
        assert result.returncode == 0, f"hop3-deploy --help failed: {result.stderr}"
        assert "hop3" in result.stdout.lower() or "deploy" in result.stdout.lower()

    def test_deploy_requires_target(self) -> None:
        """Test hop3-deploy without --docker or --host fails gracefully.

        The conftest's pytest_configure strips ambient deploy-target env vars
        (HOP3_DEV_HOST etc.), so a bare `hop3-deploy-server` here can't inherit a
        target and deploy to a real host — it must report "no target".
        """
        result = subprocess.run(
            ["hop3-deploy-server"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Should fail but with a helpful message
        assert result.returncode != 0
        # Should mention needing a target
        output = (result.stdout + result.stderr).lower()
        assert "docker" in output or "host" in output or "target" in output
