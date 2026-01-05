# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: PT012

"""Tests for server-side CLI admin commands (hop3-server admin:*)."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, Mock, patch

import pytest

from hop3.orm import Role, User
from hop3.server.cli.admin import AdminCreate, AdminList, AdminResetPassword, AdminToken


@pytest.fixture
def mock_db_session():
    """Create a mock database session context manager."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = Mock(spec=User)
    user.username = "testuser"
    user.email = "test@example.com"
    user.active = True
    user.is_admin = True
    user.login_count = 5
    user.roles = []
    return user


@pytest.fixture
def mock_admin_role():
    """Create a mock admin role."""
    role = Mock(spec=Role)
    role.name = "admin"
    role.description = "Administrator role"
    return role


class TestAdminCreate:
    """Tests for admin:create command."""

    def test_create_admin_success(self, mock_db_session, mock_admin_role, monkeypatch):
        """Test successful admin user creation."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        # Mock get_session context manager
        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.filter_by.return_value.first.side_effect = [
            None,  # Check username exists
            None,  # Check email exists
            mock_admin_role,  # Get admin role
        ]

        # Create a mock user that properly handles roles
        mock_new_user = MagicMock()
        mock_new_user.roles = []  # Use a real list instead of mock

        # Capture stdout
        captured_output = io.StringIO()

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["password123", "password123"],
            ),
            patch("hop3.server.cli.admin.User", return_value=mock_new_user),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminCreate()
            cmd.run(
                username="newadmin", email="admin@example.com", password_stdin=False
            )

        output = captured_output.getvalue()
        assert "Admin user 'newadmin' created successfully" in output
        assert "Token:" in output or "eyJ" in output  # JWT token present

    def test_create_admin_password_stdin(
        self, mock_db_session, mock_admin_role, monkeypatch
    ):
        """Test admin creation with password from stdin."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.filter_by.return_value.first.side_effect = [
            None,
            None,
            mock_admin_role,
        ]

        # Create a mock user that properly handles roles
        mock_new_user = MagicMock()
        mock_new_user.roles = []  # Use a real list instead of mock

        captured_output = io.StringIO()

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch("sys.stdin", io.StringIO("password123\n")),
            patch("hop3.server.cli.admin.User", return_value=mock_new_user),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminCreate()
            cmd.run(username="newadmin", email="admin@example.com", password_stdin=True)

        output = captured_output.getvalue()
        assert "Admin user 'newadmin' created successfully" in output

    def test_create_admin_username_exists(self, mock_user, monkeypatch):
        """Test error when username already exists."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_user
        )

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["password123", "password123"],
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd = AdminCreate()  # noqa: PT012
            cmd.run(username="testuser", email="new@example.com", password_stdin=False)

        assert exc_info.value.code == 1

    def test_create_admin_password_mismatch(self, monkeypatch):
        """Test error when passwords don't match."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["password123", "different"],
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd = AdminCreate()  # noqa: PT012
            cmd.run(
                username="newadmin", email="admin@example.com", password_stdin=False
            )

        assert exc_info.value.code == 1


class TestAdminToken:
    """Tests for admin:token command."""

    def test_generate_token_success(self, mock_user, monkeypatch):
        """Test successful token generation."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_user
        )

        captured_output = io.StringIO()

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminToken()
            cmd.run(username="testuser")

        output = captured_output.getvalue()
        assert "API token generated for user: testuser" in output
        assert "Token:" in output

    def test_generate_token_user_not_found(self, monkeypatch):
        """Test error when user doesn't exist."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd = AdminToken()  # noqa: PT012
            cmd.run(username="nonexistent")

        assert exc_info.value.code == 1

    def test_generate_token_disabled_user(self, mock_user, monkeypatch):
        """Test error when user is disabled."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")
        mock_user.active = False

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_user
        )

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd = AdminToken()  # noqa: PT012
            cmd.run(username="testuser")

        assert exc_info.value.code == 1


class TestAdminList:
    """Tests for admin:list command."""

    def test_list_users_success(self, mock_user, monkeypatch):
        """Test listing users."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.order_by.return_value.all.return_value = [
            mock_user
        ]

        captured_output = io.StringIO()

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminList()
            cmd.run()

        output = captured_output.getvalue()
        assert "testuser" in output
        assert "test@example.com" in output
        assert "Total users: 1" in output

    def test_list_users_empty(self, monkeypatch):
        """Test listing when no users exist."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.order_by.return_value.all.return_value = []

        captured_output = io.StringIO()

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminList()
            cmd.run()

        output = captured_output.getvalue()
        assert "No users found" in output


class TestAdminResetPassword:
    """Tests for admin:reset-password command."""

    def test_reset_password_success(self, mock_user, monkeypatch):
        """Test successful password reset."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_user
        )

        captured_output = io.StringIO()

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["newpass123", "newpass123"],
            ),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminResetPassword()
            cmd.run(username="testuser", password_stdin=False)

        output = captured_output.getvalue()
        assert "Password reset successfully" in output
        mock_user.set_password.assert_called_once_with("newpass123")

    def test_reset_password_stdin(self, mock_user, monkeypatch):
        """Test password reset with stdin."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_user
        )

        captured_output = io.StringIO()

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch("sys.stdin", io.StringIO("newpass123\n")),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminResetPassword()
            cmd.run(username="testuser", password_stdin=True)

        output = captured_output.getvalue()
        assert "Password reset successfully" in output

    def test_reset_password_user_not_found(self, monkeypatch):
        """Test error when user doesn't exist."""
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

        mock_session = MagicMock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with (
            patch("hop3.server.cli.admin.get_session", return_value=mock_session),
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["newpass123", "newpass123"],
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd = AdminResetPassword()  # noqa: PT012
            cmd.run(username="nonexistent", password_stdin=False)

        assert exc_info.value.code == 1
