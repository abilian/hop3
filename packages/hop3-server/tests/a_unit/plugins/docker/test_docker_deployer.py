# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DockerComposeDeployer."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from hop3.config import HopConfig
from hop3.core.protocols import BuildArtifact, DeploymentContext
from hop3.deployers.deployer import _apply_limits
from hop3.lib import Abort
from hop3.plugins.docker.deployer import DockerComposeDeployer
from hop3.project.hop3_config import Hop3Config

if TYPE_CHECKING:
    from pathlib import Path


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
            patch("hop3.plugins.docker.deployer.get_free_port", return_value=9999),
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

            with pytest.raises(Abort, match="'docker' binary was not found"):
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

            # destroy() makes multiple calls: compose down + network cleanup
            # Check that compose down was called
            all_calls = mock_run.call_args_list
            compose_down_call = all_calls[0]  # First call is compose down
            cmd = compose_down_call[0][0]
            assert "down" in cmd
            assert "--volumes" in cmd
            # Reclaim the app's built images too, else disk fills over many
            # deploy/destroy cycles. "all" (not "local") because Hop3 tags the
            # built service image, which "local" would skip.
            assert cmd[cmd.index("--rmi") + 1] == "all"


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
        # HOST_NAME is intentionally not set by default - apps without hostname
        # don't get proxy config (see _setup_proxy which checks for this)
        assert "HOST_NAME" not in env
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

        # ENV file is ignored and HOST_NAME is intentionally not set by default
        # Apps without hostname don't get proxy config
        assert "HOST_NAME" not in env

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

    def test_setup_proxy_propagates_exception(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ):
        """Proxy/cert setup failures must surface, not be swallowed.

        A swallowed proxy error is how edrix.eu shipped a self-signed cert under
        a green deploy; the failure must propagate so the deploy fails.
        """
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

        with (
            patch(
                "hop3.plugins.docker.deployer.get_proxy_strategy",
                return_value=mock_proxy,
            ),
            pytest.raises(RuntimeError, match="Proxy configuration failed"),
        ):
            deployer._setup_proxy(8080)


class TestRewriteHostForDocker:
    """Tests for the localhost → host.docker.internal rewriter.

    The rewrite is applied to ALL env var values (not a fixed
    whitelist) so app-specific names like GF_DATABASE_HOST,
    SMTP_HOST, MY_DB_URL are handled correctly.
    """

    @pytest.fixture
    def deployer(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ) -> DockerComposeDeployer:
        context = DeploymentContext(
            app_name="test",
            source_path=tmp_path,
            app_config={},
        )
        return DockerComposeDeployer(context, docker_artifact)

    def test_rewrites_bare_host_port(self, deployer: DockerComposeDeployer):
        """GF_DATABASE_HOST-style ``host:port`` value."""
        assert (
            deployer._rewrite_host_for_docker("127.0.0.1:5432")
            == "host.docker.internal:5432"
        )
        assert (
            deployer._rewrite_host_for_docker("localhost:8080")
            == "host.docker.internal:8080"
        )

    def test_rewrites_url_with_userinfo(self, deployer: DockerComposeDeployer):
        """DATABASE_URL-style postgres://user:pass@host:port/db."""
        got = deployer._rewrite_host_for_docker(
            "postgresql://u:p@127.0.0.1:5432/dbname"
        )
        assert got == "postgresql://u:p@host.docker.internal:5432/dbname"

    def test_rewrites_url_without_userinfo(self, deployer: DockerComposeDeployer):
        """redis://host:port/0 — no userinfo."""
        got = deployer._rewrite_host_for_docker("redis://localhost:6379/0")
        assert got == "redis://host.docker.internal:6379/0"

    def test_rewrites_bare_host_only(self, deployer: DockerComposeDeployer):
        """PGHOST is just the host name, nothing else."""
        assert deployer._rewrite_host_for_docker("127.0.0.1") == "host.docker.internal"
        assert deployer._rewrite_host_for_docker("localhost") == "host.docker.internal"

    def test_leaves_non_matching_values(self, deployer: DockerComposeDeployer):
        """Substrings that happen to contain 'localhost' shouldn't be touched."""
        assert (
            deployer._rewrite_host_for_docker("my-localhost-fallback")
            == "my-localhost-fallback"
        )
        assert deployer._rewrite_host_for_docker("foo127.0.0.1bar") == "foo127.0.0.1bar"

    def test_leaves_non_local_values(self, deployer: DockerComposeDeployer):
        """Real remote hosts are untouched."""
        assert deployer._rewrite_host_for_docker("prod.db:5432") == "prod.db:5432"
        assert deployer._rewrite_host_for_docker("") == ""

    def test_rewrites_comma_separated_hosts(self, deployer: DockerComposeDeployer):
        """Redis Sentinel-style multi-host value."""
        got = deployer._rewrite_host_for_docker("127.0.0.1:26379,remote:26379")
        assert got == "host.docker.internal:26379,remote:26379"


class TestPruneDanglingImages:
    """A (re)deploy reclaims the image it superseded — dangling-only."""

    @pytest.fixture
    def deployer(
        self, tmp_path: Path, docker_artifact: BuildArtifact
    ) -> DockerComposeDeployer:
        context = DeploymentContext(
            app_name="test", source_path=tmp_path, app_config={}
        )
        return DockerComposeDeployer(context, docker_artifact)

    def test_prunes_dangling_only_never_base_or_cache(
        self, deployer: DockerComposeDeployer
    ):
        with patch("hop3.plugins.docker.deployer.subprocess.run") as mock_run:
            deployer._prune_dangling_images()

        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert cmd == ["docker", "image", "prune", "-f"]
        # NOT -a/-af (which would drop base images) and NOT a builder-cache prune.
        assert "-a" not in cmd
        assert "-af" not in cmd
        assert "builder" not in cmd

    def test_prune_failure_never_fails_the_deploy(
        self, deployer: DockerComposeDeployer
    ):
        with patch(
            "hop3.plugins.docker.deployer.subprocess.run",
            side_effect=OSError("docker not found"),
        ):
            deployer._prune_dangling_images()  # must not raise


class TestDockerComposeLimits:
    """[limits] resource caps are rendered into the generated compose (ADR 046)."""

    def _deployer(self, tmp_path, docker_artifact, limits):
        context = DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={"hop3_config": {"limits": limits}},
        )
        return DockerComposeDeployer(context, docker_artifact)

    def test_compose_includes_resource_limits(self, tmp_path, docker_artifact):
        deployer = self._deployer(
            tmp_path, docker_artifact, {"memory": "512M", "cpu": 1.5, "processes": 256}
        )
        compose = deployer._generate_compose_file().read_text()
        assert "mem_limit: 512m" in compose  # lowercased for compose
        assert "cpus: 1.5" in compose
        assert "pids_limit: 256" in compose
        # Swap-off parity with the native cgroup mapping (memory.swap.max=0).
        assert "memswap_limit: 512m" in compose
        assert "mem_swappiness: 0" in compose

    def test_compose_has_no_limits_when_none(self, tmp_path, docker_artifact):
        deployer = self._deployer(tmp_path, docker_artifact, {})
        compose = deployer._generate_compose_file().read_text()
        assert "mem_limit" not in compose
        assert "pids_limit" not in compose

    def test_limits_section_lowercases_memory(self, tmp_path, docker_artifact):
        deployer = self._deployer(tmp_path, docker_artifact, {"memory": "1G"})
        assert "mem_limit: 1g" in deployer._compose_limits_section()


class _FakeLoader:
    """Minimal ConfigLoader stub for a known server-wide [limits] policy."""

    def __init__(self, values: dict) -> None:
        self.values = values

    def get_str(self, key, default=""):
        return self.values.get(key, default)

    def get_bool(self, key, default=False):
        return self.values.get(key, default)

    def get_int(self, key, default=0):
        return self.values.get(key, default)

    def get_float(self, key, default=0.0):
        return self.values.get(key, default)


@pytest.fixture
def set_limits_config():
    """Install a HopConfig with a given server-wide [limits] policy; reset after."""

    def _set(**values):
        HopConfig.set_instance(HopConfig(config_loader=_FakeLoader(values)))

    yield _set
    HopConfig.reset_instance()


class TestApplyLimits:
    """Server-side resolve + record + builder dispatch for [limits] (ADR 046 P2)."""

    def _ctx(self, tmp_path, limits):
        return DeploymentContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={"hop3_config": {"limits": dict(limits)}},
        )

    def test_docker_resolves_records_and_stashes(self, tmp_path, set_limits_config):
        set_limits_config()  # empty server policy
        app = SimpleNamespace(limits_enforced="", limits_detail="")
        hc = Hop3Config.from_str('[limits]\nmemory = "512M"\ncpu = 1.5\n')
        ctx = self._ctx(tmp_path, hc.limits)
        _apply_limits(app, hc, "docker", ctx)
        assert app.limits_enforced == "docker"
        assert "memory=512M" in app.limits_detail
        assert ctx.app_config["hop3_config"]["limits"] == {"memory": "512M", "cpu": 1.5}

    def test_docker_no_limits_records_nothing(self, tmp_path, set_limits_config):
        set_limits_config()
        app = SimpleNamespace(limits_enforced="", limits_detail="")
        hc = Hop3Config.from_str('[metadata]\nid = "x"\n')
        ctx = self._ctx(tmp_path, {})
        _apply_limits(app, hc, "docker", ctx)
        assert app.limits_enforced == ""

    def test_docker_applies_server_default(self, tmp_path, set_limits_config):
        # An app that declares no memory gets the operator's server default.
        set_limits_config(LIMITS_DEFAULT_MEMORY="512M")
        app = SimpleNamespace(limits_enforced="", limits_detail="")
        hc = Hop3Config.from_str('[metadata]\nid = "x"\n')
        ctx = self._ctx(tmp_path, {})
        _apply_limits(app, hc, "docker", ctx)
        assert ctx.app_config["hop3_config"]["limits"]["memory"] == "512M"
        assert app.limits_enforced == "docker"

    def test_docker_over_ceiling_aborts(self, tmp_path, set_limits_config):
        set_limits_config(LIMITS_CEILING_MEMORY="2G")
        app = SimpleNamespace(limits_enforced="", limits_detail="")
        hc = Hop3Config.from_str('[limits]\nmemory = "4G"\n')
        ctx = self._ctx(tmp_path, hc.limits)
        with pytest.raises(Abort, match="exceeds the server ceiling"):
            _apply_limits(app, hc, "docker", ctx)

    def test_native_validates_but_records_nothing(self, tmp_path, set_limits_config):
        # Native resolves (for the early ceiling check) but does NOT record here —
        # the cap is applied post-start by enforce_native_limits.
        set_limits_config()
        app = SimpleNamespace(limits_enforced="", limits_detail="")
        hc = Hop3Config.from_str('[limits]\nmemory = "512M"\n')
        ctx = self._ctx(tmp_path, hc.limits)
        _apply_limits(app, hc, "local", ctx)  # no raise
        assert app.limits_enforced == ""
        # native does not stash into the docker compose dict
        assert ctx.app_config["hop3_config"]["limits"] == {"memory": "512M"}

    def test_native_over_ceiling_aborts_before_build(self, tmp_path, set_limits_config):
        # The ceiling check runs for native too, so a bad cap fails before build.
        set_limits_config(LIMITS_CEILING_MEMORY="2G")
        app = SimpleNamespace(limits_enforced="", limits_detail="")
        hc = Hop3Config.from_str('[limits]\nmemory = "4G"\n')
        ctx = self._ctx(tmp_path, hc.limits)
        with pytest.raises(Abort, match="exceeds the server ceiling"):
            _apply_limits(app, hc, "local", ctx)
