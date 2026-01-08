# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for hop3_installer.deployer.config module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3_installer.deployer.config import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_USER,
    DEFAULT_BRANCH,
    DEFAULT_SSH_USER,
    DOCKER_CONTAINER_NAME,
    DOCKER_IMAGE,
    DeployConfig,
)

if TYPE_CHECKING:
    from pathlib import Path

# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_default_branch(self):
        """DEFAULT_BRANCH should be devel."""
        assert DEFAULT_BRANCH == "devel"

    def test_default_ssh_user(self):
        """DEFAULT_SSH_USER should be root."""
        assert DEFAULT_SSH_USER == "root"

    def test_default_admin_user(self):
        """DEFAULT_ADMIN_USER should be admin."""
        assert DEFAULT_ADMIN_USER == "admin"

    def test_docker_image(self):
        """DOCKER_IMAGE should be ubuntu:24.04."""
        assert DOCKER_IMAGE == "ubuntu:24.04"

    def test_docker_container_name(self):
        """DOCKER_CONTAINER_NAME should be hop3-dev."""
        assert DOCKER_CONTAINER_NAME == "hop3-dev"


# =============================================================================
# DeployConfig Tests
# =============================================================================


class TestDeployConfig:
    """Tests for DeployConfig dataclass."""

    def test_default_values(self):
        """DeployConfig should have sensible defaults."""
        config = DeployConfig()

        assert config.host is None
        assert config.use_docker is False
        assert config.docker_image == DOCKER_IMAGE
        assert config.docker_container == DOCKER_CONTAINER_NAME
        assert config.ssh_user == DEFAULT_SSH_USER
        assert config.branch == DEFAULT_BRANCH
        assert config.use_local_code is False
        assert config.admin_user == DEFAULT_ADMIN_USER
        assert config.admin_email == DEFAULT_ADMIN_EMAIL
        assert config.verbose is False
        assert config.quiet is False

    def test_admin_password_generated_if_empty(self):
        """DeployConfig should generate admin password if not provided."""
        config = DeployConfig()
        assert config.admin_password != ""
        assert len(config.admin_password) > 10  # Should be reasonably long

    def test_admin_password_preserved_if_provided(self):
        """DeployConfig should preserve provided admin password."""
        config = DeployConfig(admin_password="my_secret_password")
        assert config.admin_password == "my_secret_password"

    def test_default_features_is_docker(self):
        """DeployConfig should default to docker feature."""
        config = DeployConfig()
        assert config.with_features == ["docker"]

    def test_custom_features_preserved(self):
        """DeployConfig should preserve custom features."""
        config = DeployConfig(with_features=["redis", "mysql"])
        assert config.with_features == ["redis", "mysql"]


class TestDeployConfigSshTarget:
    """Tests for DeployConfig.ssh_target property."""

    def test_ssh_target_format(self):
        """ssh_target should return user@host format."""
        config = DeployConfig(host="example.com", ssh_user="deploy")
        assert config.ssh_target == "deploy@example.com"

    def test_ssh_target_with_default_user(self):
        """ssh_target should use default user when not specified."""
        config = DeployConfig(host="server.local")
        assert config.ssh_target == "root@server.local"

    def test_ssh_target_raises_without_host(self):
        """ssh_target should raise ValueError when host not set."""
        config = DeployConfig()
        with pytest.raises(ValueError, match="Host not set"):
            _ = config.ssh_target


class TestDeployConfigValidate:
    """Tests for DeployConfig.validate() method."""

    def test_validate_no_target(self):
        """validate() should error when no target specified."""
        config = DeployConfig()
        errors = config.validate()
        assert len(errors) > 0
        assert any("target" in e.lower() for e in errors)

    def test_validate_with_host(self, mock_project_root: Path):
        """validate() should pass with host specified."""
        config = DeployConfig(host="example.com", project_root=mock_project_root)
        # Create a dummy installer file
        dist = mock_project_root / "dist"
        dist.mkdir()
        (dist / "install-server.py").write_text("# installer")

        errors = config.validate()
        # May still have errors for missing installer, but no target error
        assert not any("No target specified" in e for e in errors)

    def test_validate_with_docker(self):
        """validate() should pass with docker mode."""
        config = DeployConfig(use_docker=True)
        errors = config.validate()
        # Docker mode doesn't need host
        assert not any("No target specified" in e for e in errors)

    def test_validate_verbose_and_quiet_conflict(self):
        """validate() should error when both verbose and quiet."""
        config = DeployConfig(use_docker=True, verbose=True, quiet=True)
        errors = config.validate()
        assert any("verbose" in e.lower() and "quiet" in e.lower() for e in errors)

    def test_validate_local_code_missing_package(self, tmp_path: Path):
        """validate() should error when local code path doesn't exist."""
        config = DeployConfig(
            use_docker=True,
            use_local_code=True,
            project_root=tmp_path,
        )
        # tmp_path doesn't have packages/hop3-server
        errors = config.validate()
        assert any("not found" in e.lower() for e in errors)


class TestDeployConfigFromEnv:
    """Tests for DeployConfig.from_env()."""

    def test_from_env_defaults(self, clean_env):
        """from_env() should use defaults when no env vars set."""
        config = DeployConfig.from_env()

        assert config.host is None
        assert config.use_docker is False
        assert config.ssh_user == DEFAULT_SSH_USER
        assert config.branch == DEFAULT_BRANCH

    def test_from_env_dev_host(self, clean_env):
        """from_env() should read HOP3_DEV_HOST."""
        clean_env["HOP3_DEV_HOST"] = "dev.example.com"
        config = DeployConfig.from_env()
        assert config.host == "dev.example.com"

    def test_from_env_test_server_fallback(self, clean_env):
        """from_env() should fall back to HOP3_TEST_SERVER."""
        clean_env["HOP3_TEST_SERVER"] = "test.example.com"
        config = DeployConfig.from_env()
        assert config.host == "test.example.com"

    def test_from_env_docker(self, clean_env):
        """from_env() should read HOP3_DOCKER."""
        clean_env["HOP3_DOCKER"] = "1"
        config = DeployConfig.from_env()
        assert config.use_docker is True

    def test_from_env_ssh_user(self, clean_env):
        """from_env() should read HOP3_SSH_USER."""
        clean_env["HOP3_SSH_USER"] = "deploy"
        config = DeployConfig.from_env()
        assert config.ssh_user == "deploy"

    def test_from_env_branch(self, clean_env):
        """from_env() should read HOP3_BRANCH."""
        clean_env["HOP3_BRANCH"] = "feature-branch"
        config = DeployConfig.from_env()
        assert config.branch == "feature-branch"

    def test_from_env_local_code(self, clean_env):
        """from_env() should read HOP3_LOCAL."""
        clean_env["HOP3_LOCAL"] = "true"
        config = DeployConfig.from_env()
        assert config.use_local_code is True

    def test_from_env_clean(self, clean_env):
        """from_env() should read HOP3_CLEAN."""
        clean_env["HOP3_CLEAN"] = "1"
        config = DeployConfig.from_env()
        assert config.clean_before is True

    def test_from_env_with_features(self, clean_env):
        """from_env() should read HOP3_WITH as comma-separated list."""
        clean_env["HOP3_WITH"] = "redis, mysql, docker"
        config = DeployConfig.from_env()
        assert config.with_features == ["redis", "mysql", "docker"]

    def test_from_env_admin_settings(self, clean_env):
        """from_env() should read admin settings."""
        clean_env["HOP3_ADMIN_DOMAIN"] = "admin.example.com"
        clean_env["HOP3_ADMIN_USER"] = "superadmin"
        clean_env["HOP3_ADMIN_EMAIL"] = "admin@test.com"
        clean_env["HOP3_ADMIN_PASSWORD"] = "secret123"

        config = DeployConfig.from_env()

        assert config.admin_domain == "admin.example.com"
        assert config.admin_user == "superadmin"
        assert config.admin_email == "admin@test.com"
        assert config.admin_password == "secret123"

    def test_from_env_verbose(self, clean_env):
        """from_env() should read HOP3_VERBOSE."""
        clean_env["HOP3_VERBOSE"] = "true"
        config = DeployConfig.from_env()
        assert config.verbose is True

    def test_from_env_quiet(self, clean_env):
        """from_env() should read HOP3_QUIET."""
        clean_env["HOP3_QUIET"] = "1"
        config = DeployConfig.from_env()
        assert config.quiet is True


class TestDeployConfigPaths:
    """Tests for DeployConfig path properties."""

    def test_packages_path(self, mock_project_root: Path):
        """packages_path should return project_root/packages."""
        config = DeployConfig(project_root=mock_project_root)
        assert config.packages_path == mock_project_root / "packages"

    def test_server_package_path(self, mock_project_root: Path):
        """server_package_path should return packages/hop3-server."""
        config = DeployConfig(project_root=mock_project_root)
        assert (
            config.server_package_path == mock_project_root / "packages" / "hop3-server"
        )

    def test_dist_path(self, mock_project_root: Path):
        """dist_path should return project_root/dist."""
        config = DeployConfig(project_root=mock_project_root)
        assert config.dist_path == mock_project_root / "dist"
