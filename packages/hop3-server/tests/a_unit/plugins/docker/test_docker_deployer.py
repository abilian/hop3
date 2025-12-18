# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DockerComposeDeployer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hop3.core.protocols import BuildArtifact, DeploymentContext
from hop3.lib import Abort
from hop3.plugins.docker.deployer import DockerComposeDeployer


@pytest.fixture
def docker_artifact() -> BuildArtifact:
    """Create a docker-image artifact for testing."""
    return BuildArtifact(
        kind="docker-image",
        location="hop3/test-app:latest",
        metadata={"app_name": "test-app", "exposed_ports": [8080]},
    )


@pytest.fixture
def non_docker_artifact() -> BuildArtifact:
    """Create a non-docker artifact for testing."""
    return BuildArtifact(
        kind="virtualenv",
        location="/path/to/venv",
        metadata={},
    )


class TestDockerComposeDeployerAccept:
    """Tests for DockerComposeDeployer.accept() method."""

    def test_accept_with_docker_artifact_and_compose_file(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should accept docker-image artifact with docker-compose.yml."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        assert deployer.accept() is True

    def test_accept_with_compose_yaml(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should accept with docker-compose.yaml extension."""
        (tmp_path / "docker-compose.yaml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        assert deployer.accept() is True

    def test_accept_with_compose_yml(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should accept with compose.yml (new Docker Compose format)."""
        (tmp_path / "compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        assert deployer.accept() is True

    def test_reject_non_docker_artifact(
        self, tmp_path: Path, non_docker_artifact: BuildArtifact
    ):
        """Should reject non-docker artifacts."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, non_docker_artifact)

        assert deployer.accept() is False

    def test_accept_without_compose_file(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should accept docker artifact even without compose file.

        Hop3 generates docker-compose.yml automatically if not provided.
        See ADR 033 for details.
        """
        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        assert deployer.accept() is True


class TestDockerComposeDeployerDeploy:
    """Tests for DockerComposeDeployer.deploy() method."""

    def test_deploy_success(self, tmp_path: Path, docker_artifact: BuildArtifact):
        """Should return DeploymentInfo on successful deploy."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with (
            patch("subprocess.run") as mock_run,
            patch(
                "hop3.plugins.docker.deployer.get_free_port", return_value=9999
            ) as mock_port,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            info = deployer.deploy()

            assert info.protocol == "http"
            assert info.address == "127.0.0.1"
            assert info.port == 9999  # From allocated port

            # Verify docker compose up was called (first call)
            assert mock_run.call_count >= 1
            first_call = mock_run.call_args_list[0]
            cmd = first_call[0][0]
            assert "docker" in cmd
            assert "compose" in cmd
            assert "up" in cmd

    def test_deploy_with_scaling(self, tmp_path: Path, docker_artifact: BuildArtifact):
        """Should include scaling arguments when deltas provided."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with (
            patch("subprocess.run") as mock_run,
            patch("hop3.plugins.docker.deployer.get_free_port", return_value=9999),
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            deployer.deploy(deltas={"web": 3})

            # Check the first call (docker compose up) for scaling args
            first_call = mock_run.call_args_list[0]
            cmd = first_call[0][0]
            assert "--scale" in cmd
            assert "web=3" in cmd

    def test_deploy_docker_not_found(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should raise Abort when Docker is not installed."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            with pytest.raises(Abort, match="Docker Compose not found"):
                deployer.deploy()


class TestDockerComposeDeployerLifecycle:
    """Tests for lifecycle methods (start, stop, restart, destroy)."""

    def test_stop(self, tmp_path: Path, docker_artifact: BuildArtifact):
        """Should run docker compose stop."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            deployer.stop()

            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "stop" in cmd

    def test_destroy(self, tmp_path: Path, docker_artifact: BuildArtifact):
        """Should run docker compose down with cleanup flags."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            deployer.destroy()

            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "down" in cmd
            assert "--volumes" in cmd


class TestDockerComposeDeployerStatus:
    """Tests for status methods."""

    def test_check_status_running(self, tmp_path: Path, docker_artifact: BuildArtifact):
        """Should return True when containers are running."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="running\nrunning\n",
            )

            assert deployer.check_status() is True

    def test_check_status_not_running(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should return False when no containers are running."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="exited\n",
            )

            assert deployer.check_status() is False

    def test_check_status_docker_error(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should return False on Docker errors."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            assert deployer.check_status() is False

    def test_get_status_detailed(self, tmp_path: Path, docker_artifact: BuildArtifact):
        """Should return detailed status with service info."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="test-app-web-1\trunning\tUp 5 minutes\n",
            )

            status = deployer.get_status()

            assert status["running"] is True
            assert "test-app-web-1" in status["services"]
            assert status["services"]["test-app-web-1"]["state"] == "running"


class TestDockerComposeDeployerPortDiscovery:
    """Tests for port discovery."""

    def test_discover_port_from_metadata(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should use port from artifact metadata."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        port = deployer._discover_port()

        assert port == 8080

    def test_discover_port_fallback(self, tmp_path: Path):
        """Should fall back to 8080 when port not discoverable."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        artifact = BuildArtifact(
            kind="docker-image",
            location="hop3/test-app:latest",
            metadata={},  # No exposed_ports
        )
        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, artifact)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            port = deployer._discover_port()

            assert port == 8080


class TestDockerComposeDeployerProxyIntegration:
    """Tests for proxy integration methods."""

    def test_make_proxy_env_basic(self, tmp_path: Path, docker_artifact: BuildArtifact):
        """Should create environment with required proxy variables."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        env = deployer._make_proxy_env(8080)

        assert env["APP"] == "test-app"
        assert env["PORT"] == "8080"
        assert env["BIND_ADDRESS"] == "127.0.0.1"
        assert env["HOST_NAME"] == "_"  # Default when not configured
        assert "NGINX_IPV4_ADDRESS" in env

    def test_make_proxy_env_ignores_env_file(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should NOT load HOST_NAME from ENV file (removed feature)."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
        # ENV file exists but should be ignored - HOST_NAME comes from ORM only
        (tmp_path / "ENV").write_text("HOST_NAME=myapp.example.com\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        env = deployer._make_proxy_env(8080)

        # ENV file is ignored, so HOST_NAME should be default "_"
        assert env["HOST_NAME"] == "_"

    def test_make_proxy_env_with_app_runtime_env(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should load HOST_NAME from App runtime environment."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        # Create a mock App with runtime environment
        mock_app = MagicMock()
        mock_app.get_runtime_env.return_value = {"HOST_NAME": "runtime.example.com"}

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
            app=mock_app,
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        env = deployer._make_proxy_env(8080)

        assert env["HOST_NAME"] == "runtime.example.com"

    def test_get_workers(self, tmp_path: Path, docker_artifact: BuildArtifact):
        """Should return web worker for Docker apps."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        workers = deployer._get_workers()

        assert workers == {"web": "docker-compose"}

    def test_setup_proxy_skipped_when_no_app(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should skip proxy setup when no App in context."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
            app=None,  # No app
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with patch("hop3.plugins.docker.deployer.get_proxy_strategy") as mock_get_proxy:
            deployer._setup_proxy(8080)

            # Proxy strategy should NOT be called
            mock_get_proxy.assert_not_called()

    def test_setup_proxy_skipped_when_hostname_is_catchall(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should skip proxy setup when HOST_NAME is '_'."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        mock_app = MagicMock()
        mock_app.get_runtime_env.return_value = {}  # No HOST_NAME

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
            app=mock_app,
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        with patch("hop3.plugins.docker.deployer.get_proxy_strategy") as mock_get_proxy:
            deployer._setup_proxy(8080)

            # Proxy strategy should NOT be called
            mock_get_proxy.assert_not_called()

    def test_setup_proxy_called_when_hostname_configured(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should call proxy setup when HOST_NAME is configured."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        mock_app = MagicMock()
        mock_app.get_runtime_env.return_value = {"HOST_NAME": "myapp.example.com"}

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
            app=mock_app,
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        mock_proxy = MagicMock()
        with patch(
            "hop3.plugins.docker.deployer.get_proxy_strategy", return_value=mock_proxy
        ) as mock_get_proxy:
            deployer._setup_proxy(8080)

            # Proxy strategy should be called
            mock_get_proxy.assert_called_once()
            mock_proxy.setup.assert_called_once()

            # Verify proxy was called with correct arguments
            call_args = mock_get_proxy.call_args
            assert call_args[0][0] == mock_app  # First arg is app
            assert call_args[0][2] == {"web": "docker-compose"}  # Third arg is workers

    def test_setup_proxy_handles_exception(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Should handle proxy setup exceptions gracefully."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n")

        mock_app = MagicMock()
        mock_app.get_runtime_env.return_value = {"HOST_NAME": "myapp.example.com"}

        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
            app=mock_app,
        )
        deployer = DockerComposeDeployer(context, docker_artifact)

        mock_proxy = MagicMock()
        mock_proxy.setup.side_effect = RuntimeError("Proxy configuration failed")

        with patch(
            "hop3.plugins.docker.deployer.get_proxy_strategy", return_value=mock_proxy
        ):
            # Should not raise - exception is caught and logged
            deployer._setup_proxy(8080)
