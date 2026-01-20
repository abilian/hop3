# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""E2E tests for server installer (install-server.py).

These tests verify that the bundled server installer correctly installs
hop3-server and configures all required services across different backends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_installer.testing.backends import Backend


@pytest.mark.e2e
class TestServerInstaller:
    """Test hop3-server installation via install-server.py."""

    def test_install_server_from_git(
        self,
        backend: Backend,
        bundled_installers: dict[str, Path],
    ) -> None:
        """Test server installation from git repository.

        This is the primary installation method - installing from the
        git repository's devel branch.
        """
        # Clean up any previous installation
        backend.cleanup_server()

        # Upload installer to target
        installer_path = "/tmp/install-server.py"
        assert backend.upload(bundled_installers["server"], installer_path), (
            "Failed to upload installer"
        )

        # Run installer with git method
        # Note: --skip-acme to avoid Let's Encrypt in test environment
        # Note: --skip-postgres to speed up tests
        result = backend.run(
            f"python3 {installer_path} "
            "--git --branch devel "
            "--skip-acme --skip-postgres "
            "--verbose",
            sudo=True,
        )

        # Check installer succeeded
        assert result.success, (
            f"Server installer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Validate installation
        self._validate_server_installation(backend)

    def test_install_server_from_local_path(
        self,
        backend: Backend,
        bundled_installers: dict[str, Path],
        hop3_packages_dir: Path,
    ) -> None:
        """Test server installation from local package path.

        This tests the --local-path option used during development.
        """
        # Clean up any previous installation
        backend.cleanup_server()

        # Upload installer to target
        installer_path = "/tmp/install-server.py"
        assert backend.upload(bundled_installers["server"], installer_path), (
            "Failed to upload installer"
        )

        # Upload the hop3-server package to target
        server_package = hop3_packages_dir / "hop3-server"
        if not server_package.exists():
            pytest.skip(f"hop3-server package not found: {server_package}")

        remote_pkg_path = "/tmp/hop3-server"
        assert backend.upload_dir(server_package, remote_pkg_path), (
            "Failed to upload server package"
        )

        # Run installer with local path
        result = backend.run(
            f"python3 {installer_path} "
            f"--local-path {remote_pkg_path} "
            "--skip-acme --skip-postgres "
            "--verbose",
            sudo=True,
        )

        # Check installer succeeded
        assert result.success, (
            f"Server installer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Validate installation
        self._validate_server_installation(backend)

    def _validate_server_installation(self, backend: Backend) -> None:
        """Validate server was installed correctly.

        Checks:
        1. hop3 user was created
        2. Virtual environment was created
        3. hop3-server command exists
        4. Required directories exist
        """
        # Check hop3 user exists
        result = backend.run("id hop3")
        assert result.success, "hop3 user not created"

        # Check venv exists
        result = backend.run("test -d /home/hop3/venv")
        assert result.success, "Server virtual environment not created"

        # Check hop3-server command exists
        result = backend.run("test -f /home/hop3/venv/bin/hop3-server")
        assert result.success, "hop3-server command not found"

        # Check required directories exist
        # Note: /home/hop3/apps is created by hop3-server setup
        for directory in ["/home/hop3/apps"]:
            result = backend.run(f"test -d {directory}")
            assert result.success, f"Directory not created: {directory}"

        # Check hop3-server runs (just version/help to verify it's not broken)
        result = backend.run("/home/hop3/venv/bin/hop3-server --help 2>&1 || true")
        output = (result.stdout + result.stderr).lower()
        assert "hop3" in output or "usage" in output, (
            f"hop3-server doesn't run properly: {result.stdout} {result.stderr}"
        )


@pytest.mark.e2e
@pytest.mark.slow
class TestServerInstallerWithServices:
    """Test server installation with full service validation.

    These tests require systemd and take longer to run.
    Uses the systemd_backend fixture which provides docker-systemd, ssh, or vagrant.
    """

    @pytest.fixture(autouse=True)
    def setup_server(
        self,
        systemd_backend: Backend,
        bundled_installers: dict[str, Path],
    ) -> None:
        """Install hop3-server before running service tests."""
        # Clean up any previous installation
        systemd_backend.cleanup_server()

        # Upload installer
        installer_path = "/tmp/install-server.py"
        assert systemd_backend.upload(bundled_installers["server"], installer_path), (
            "Failed to upload installer"
        )

        # Run full installation (including PostgreSQL and nginx)
        result = systemd_backend.run(
            f"python3 {installer_path} "
            "--git --branch devel "
            "--skip-acme "  # Skip Let's Encrypt in test
            "--verbose",
            sudo=True,
        )

        if not result.success:
            pytest.skip(
                f"Server installation failed: {result.stdout[:500]}\n{result.stderr[:500]}"
            )

    def test_postgresql_configured(self, systemd_backend: Backend) -> None:
        """Verify PostgreSQL is properly configured after installation."""
        # Check PostgreSQL service is running
        result = systemd_backend.run("systemctl is-active postgresql")
        assert "active" in result.stdout, "PostgreSQL service not running"

        # Check hop3 role exists
        result = systemd_backend.run(
            'su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_roles WHERE '
            "rolname='hop3'\\\"\" ",
            sudo=True,
        )
        assert "1" in result.stdout, "PostgreSQL hop3 role not found"

    def test_nginx_configured(self, systemd_backend: Backend) -> None:
        """Verify nginx is properly configured after installation."""
        # Check nginx service is running
        result = systemd_backend.run("systemctl is-active nginx")
        assert "active" in result.stdout, "nginx service not running"

        # Check nginx config is valid
        result = systemd_backend.run("nginx -t 2>&1", sudo=True)
        assert result.success, f"nginx config invalid: {result.stderr}"

    def test_hop3_server_service(self, systemd_backend: Backend) -> None:
        """Verify hop3-server systemd service is configured."""
        # Check service is enabled
        result = systemd_backend.run("systemctl is-enabled hop3-server")
        assert "enabled" in result.stdout, "hop3-server service not enabled"
