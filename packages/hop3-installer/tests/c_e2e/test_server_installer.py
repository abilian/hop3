# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""E2E tests for server installer (install-server.py).

These tests verify that the bundled server installer correctly installs
hop3-server and configures all required services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .conftest import docker_copy, docker_copy_dir, docker_exec

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.e2e
class TestServerInstaller:
    """Test hop3-server installation via install-server.py."""

    def test_install_server_from_git(
        self,
        docker_container: str,
        bundled_installers: dict[str, Path],
    ) -> None:
        """Test server installation from git repository.

        This is the primary installation method - installing from the
        git repository's devel branch.
        """
        # Copy installer to container
        docker_copy(
            docker_container,
            bundled_installers["server"],
            "/tmp/install-server.py",
        )

        # Run installer with git method
        # Note: --skip-acme to avoid Let's Encrypt in test environment
        # Note: --skip-postgres to speed up tests
        result = docker_exec(
            docker_container,
            "python3 /tmp/install-server.py "
            "--git --branch devel "
            "--skip-acme --skip-postgres "
            "--verbose",
            check=False,
        )

        # Check installer succeeded
        assert result.returncode == 0, (
            f"Server installer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Validate installation
        self._validate_server_installation(docker_container)

    def test_install_server_from_local_path(
        self,
        docker_container: str,
        bundled_installers: dict[str, Path],
        hop3_packages_dir: Path,
    ) -> None:
        """Test server installation from local package path.

        This tests the --local-path option used during development.
        """
        # Copy installer to container
        docker_copy(
            docker_container,
            bundled_installers["server"],
            "/tmp/install-server.py",
        )

        # Copy the hop3-server package to container
        server_package = hop3_packages_dir / "hop3-server"
        if not server_package.exists():
            pytest.skip(f"hop3-server package not found: {server_package}")

        docker_copy_dir(docker_container, server_package, "/tmp/hop3-server")

        # Clean up any previous installation
        docker_exec(
            docker_container,
            "userdel -r hop3 2>/dev/null || true",
            check=False,
        )

        # Run installer with local path
        result = docker_exec(
            docker_container,
            "python3 /tmp/install-server.py "
            "--local-path /tmp/hop3-server "
            "--skip-acme --skip-postgres "
            "--verbose",
            check=False,
        )

        # Check installer succeeded
        assert result.returncode == 0, (
            f"Server installer failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Validate installation
        self._validate_server_installation(docker_container)

    def _validate_server_installation(self, container: str) -> None:
        """Validate server was installed correctly.

        Checks:
        1. hop3 user was created
        2. Virtual environment was created
        3. hop3-server command exists
        4. Required directories exist
        """
        # Check hop3 user exists
        result = docker_exec(container, "id hop3", check=False)
        assert result.returncode == 0, "hop3 user not created"

        # Check venv exists
        result = docker_exec(container, "test -d /home/hop3/venv", check=False)
        assert result.returncode == 0, "Server virtual environment not created"

        # Check hop3-server command exists
        result = docker_exec(
            container,
            "test -f /home/hop3/venv/bin/hop3-server",
            check=False,
        )
        assert result.returncode == 0, "hop3-server command not found"

        # Check required directories exist
        # Note: /home/hop3/apps is created by hop3-server setup
        for directory in ["/home/hop3/apps"]:
            result = docker_exec(container, f"test -d {directory}", check=False)
            assert result.returncode == 0, f"Directory not created: {directory}"

        # Check hop3-server runs (just version/help to verify it's not broken)
        result = docker_exec(
            container,
            "/home/hop3/venv/bin/hop3-server --help 2>&1 || true",
            check=False,
        )
        output = (result.stdout + result.stderr).lower()
        assert "hop3" in output or "usage" in output, (
            f"hop3-server doesn't run properly: {result.stdout} {result.stderr}"
        )


@pytest.mark.e2e
@pytest.mark.slow
class TestServerInstallerWithServices:
    """Test server installation with full service validation.

    These tests require systemd and take longer to run.
    They are skipped in basic Docker containers without systemd.
    """

    @pytest.fixture(autouse=True)
    def check_systemd(self, docker_container: str) -> None:
        """Skip tests if systemd is not available."""
        result = docker_exec(
            docker_container,
            "cat /proc/1/comm 2>/dev/null",
            check=False,
        )
        if "systemd" not in result.stdout:
            pytest.skip("systemd not available in container")

    def test_postgresql_configured(self, docker_container: str) -> None:
        """Verify PostgreSQL is properly configured after installation."""
        # Check PostgreSQL service is running
        result = docker_exec(
            docker_container,
            "systemctl is-active postgresql",
            check=False,
        )
        assert "active" in result.stdout, "PostgreSQL service not running"

        # Check hop3 role exists
        result = docker_exec(
            docker_container,
            'su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_roles WHERE rolname=\'hop3\'\\"" ',
            check=False,
        )
        assert "1" in result.stdout, "PostgreSQL hop3 role not found"

    def test_nginx_configured(self, docker_container: str) -> None:
        """Verify nginx is properly configured after installation."""
        # Check nginx service is running
        result = docker_exec(
            docker_container,
            "systemctl is-active nginx",
            check=False,
        )
        assert "active" in result.stdout, "nginx service not running"

        # Check nginx config is valid
        result = docker_exec(
            docker_container,
            "nginx -t 2>&1",
            check=False,
        )
        assert result.returncode == 0, f"nginx config invalid: {result.stderr}"

    def test_hop3_server_service(self, docker_container: str) -> None:
        """Verify hop3-server systemd service is configured."""
        # Check service is enabled
        result = docker_exec(
            docker_container,
            "systemctl is-enabled hop3-server",
            check=False,
        )
        assert "enabled" in result.stdout, "hop3-server service not enabled"
