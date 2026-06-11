# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for server-side CLI admin commands.

This module tests admin CLI commands using state-based testing approach:
- Uses real database instead of mocks
- Verifies actual database state changes
- Only mocks external I/O (getpass, stdin, stdout)
- Tests that outcomes (state) are correct, not just that methods were called
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from hop3.orm import Role, User
from hop3.server.cli.admin import AdminCreate, AdminList, AdminResetPassword, AdminToken

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.mark.integration
class TestAdminCreateIntegration:
    """Integration tests for admin:create command using state-based testing."""

    def test_create_admin_success(self, db_session: Session, monkeypatch):
        """Test successful admin user creation with real database.

        ARRANGE:
            - Set up test environment with secret key
            - Prepare real database (via db_session fixture)

        ACT:
            - Run AdminCreate.run() - uses real database via get_session()
            - Only mock external I/O (getpass for password input, stdout for output)

        ASSERT:
            - Verify user was created in database with correct attributes
            - Verify password hashing works (can authenticate)
            - Verify roles were assigned
            - Verify output message
        """
        # ARRANGE: Set up test environment
        monkeypatch.setenv(
            "HOP3_SECRET_KEY", "test-secret-key-for-unit-testing-for-token-generation"
        )

        # Capture stdout for output verification
        captured_output = io.StringIO()

        # ACT: Run command with real database
        # The command uses get_session() which uses get_session_factory() which is cached
        # Our db_engine fixture sets up the in-memory database and caches the factory
        # So the command and our test session share the same database
        with (
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["password123", "password123"],
            ),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminCreate()
            cmd.run(
                username="newadmin", email="admin@example.com", password_stdin=False
            )

        # ASSERT: Verify database state changes
        # Refresh session to see committed changes
        db_session.expire_all()
        user = db_session.query(User).filter_by(username="newadmin").first()

        # Verify user was created
        assert user is not None, "User should be created in database"
        assert user.username == "newadmin"
        assert user.email == "admin@example.com"
        assert user.active is True
        assert user.confirmed_at is not None

        # Verify password was set correctly (can authenticate)
        assert user.check_password("password123"), (
            "Password should be hashed and verifiable"
        )
        assert not user.check_password("wrongpass"), (
            "Wrong password should not authenticate"
        )

        # Verify roles were assigned
        assert len(user.roles) == 1, "User should have exactly one role"
        assert user.roles[0].name == "admin", "User should have admin role"

        # Verify admin role exists in database
        admin_role = db_session.query(Role).filter_by(name="admin").first()
        assert admin_role is not None, "Admin role should exist"
        assert admin_role.description == "Administrator role"

        # Also verify output (secondary concern)
        output = captured_output.getvalue()
        assert "Admin user 'newadmin' created successfully" in output
        assert "API Token" in output or "Token:" in output

    def test_create_admin_password_stdin(self, db_session: Session, monkeypatch):
        """Test admin creation with password from stdin.

        This tests automation scenario where password is piped in.
        """
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")
        captured_output = io.StringIO()

        # ACT
        with (
            patch("sys.stdin", io.StringIO("stdin_password123\n")),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminCreate()
            cmd.run(
                username="stdinuser", email="stdin@example.com", password_stdin=True
            )

        # ASSERT
        db_session.expire_all()
        user = db_session.query(User).filter_by(username="stdinuser").first()
        assert user is not None
        assert user.email == "stdin@example.com"
        assert user.check_password("stdin_password123")

    def test_create_admin_username_exists(self, db_session: Session, monkeypatch):
        """Test error when username already exists."""
        # ARRANGE: Create existing user
        existing_user = User(username="existing", email="existing@example.com")
        existing_user.set_password("password")
        db_session.add(existing_user)
        db_session.commit()

        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")

        # ACT + ASSERT: Should raise SystemExit
        with (
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["password123", "password123"],
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd = AdminCreate()
            cmd.run(username="existing", email="new@example.com", password_stdin=False)

        assert exc_info.value.code == 1

        # ASSERT: No new user was created
        db_session.expire_all()
        users = db_session.query(User).filter_by(email="new@example.com").all()
        assert len(users) == 0, "No user should be created with duplicate username"

    def test_create_admin_email_exists(self, db_session: Session, monkeypatch):
        """Test error when email already exists."""
        # ARRANGE: Create existing user with email
        existing_user = User(username="user1", email="duplicate@example.com")
        existing_user.set_password("password")
        db_session.add(existing_user)
        db_session.commit()

        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")

        # ACT + ASSERT
        with (
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["password123", "password123"],
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd = AdminCreate()
            cmd.run(
                username="user2", email="duplicate@example.com", password_stdin=False
            )

        assert exc_info.value.code == 1

        # ASSERT: No new user was created
        db_session.expire_all()
        users = db_session.query(User).filter_by(username="user2").all()
        assert len(users) == 0, "No user should be created with duplicate email"

    def test_create_admin_password_mismatch(self, db_session: Session, monkeypatch):
        """Test error when passwords don't match."""
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")

        # ACT + ASSERT
        with (
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["password123", "different_password"],
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd = AdminCreate()
            cmd.run(
                username="mismatch", email="mismatch@example.com", password_stdin=False
            )

        assert exc_info.value.code == 1

        # ASSERT: No user was created
        db_session.expire_all()
        user = db_session.query(User).filter_by(username="mismatch").first()
        assert user is None, "No user should be created when passwords don't match"


@pytest.mark.integration
class TestAdminTokenIntegration:
    """Integration tests for admin:token command using state-based testing."""

    def test_generate_token_success(
        self, db_session: Session, sample_user: User, monkeypatch
    ):
        """Test successful token generation.

        ARRANGE:
            - Set up test environment with secret key
            - Create a sample user in the database (via fixture)

        ACT:
            - Run AdminToken.run() to generate a token

        ASSERT:
            - Verify output contains token and success message
        """
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")
        captured_output = io.StringIO()

        # ACT
        with patch("sys.stdout", captured_output):
            cmd = AdminToken()
            cmd.run(username="testuser")

        # ASSERT
        output = captured_output.getvalue()
        assert "API token generated for user: testuser" in output
        assert "Token:" in output

    def test_generate_token_user_not_found(self, db_session: Session, monkeypatch):
        """Test error when user doesn't exist."""
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")

        # ACT + ASSERT
        with pytest.raises(SystemExit) as exc_info:
            cmd = AdminToken()
            cmd.run(username="nonexistent")

        assert exc_info.value.code == 1

    def test_generate_token_disabled_user(
        self, db_session: Session, sample_user: User, monkeypatch
    ):
        """Test error when user is disabled."""
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")

        # Mark user as inactive
        sample_user.active = False
        db_session.commit()

        # ACT + ASSERT
        with pytest.raises(SystemExit) as exc_info:
            cmd = AdminToken()
            cmd.run(username="testuser")

        assert exc_info.value.code == 1


@pytest.mark.integration
class TestAdminListIntegration:
    """Integration tests for admin:list command using state-based testing."""

    def test_list_users_success(
        self, db_session: Session, sample_user: User, monkeypatch
    ):
        """Test listing users.

        ARRANGE:
            - Set up test environment with secret key
            - Create a sample user in the database (via fixture)

        ACT:
            - Run AdminList.run() to list users

        ASSERT:
            - Verify output contains user information
            - Verify total user count
        """
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")
        captured_output = io.StringIO()

        # ACT
        with patch("sys.stdout", captured_output):
            cmd = AdminList()
            cmd.run()

        # ASSERT
        output = captured_output.getvalue()
        assert "testuser" in output
        assert "test@example.com" in output
        assert "Total users: 1" in output

    def test_list_users_empty(self, db_session: Session, monkeypatch):
        """Test listing when no users exist."""
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")
        captured_output = io.StringIO()

        # ACT
        with patch("sys.stdout", captured_output):
            cmd = AdminList()
            cmd.run()

        # ASSERT
        output = captured_output.getvalue()
        assert "No users found" in output


@pytest.mark.integration
class TestAdminResetPasswordIntegration:
    """Integration tests for admin:reset-password command using state-based testing."""

    def test_reset_password_success(
        self, db_session: Session, sample_user: User, monkeypatch
    ):
        """Test successful password reset.

        ARRANGE:
            - Set up test environment with secret key
            - Create a sample user in the database (via fixture)

        ACT:
            - Run AdminResetPassword.run() with new password

        ASSERT:
            - Verify user's password was changed
            - Verify old password no longer works
            - Verify new password works
            - Verify success output
        """
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")
        captured_output = io.StringIO()

        # Store original password for comparison
        original_password = "testpass123"
        new_password = "newpass123"

        # Verify original password works before reset
        assert sample_user.check_password(original_password)

        # ACT
        with (
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=[new_password, new_password],
            ),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminResetPassword()
            cmd.run(username="testuser", password_stdin=False)

        # ASSERT: Verify password was changed
        db_session.expire_all()
        db_session.refresh(sample_user)

        assert sample_user.check_password(new_password), "New password should work"
        assert not sample_user.check_password(original_password), (
            "Old password should not work"
        )

        # Verify output
        output = captured_output.getvalue()
        assert "Password reset successfully" in output

    def test_reset_password_stdin(
        self, db_session: Session, sample_user: User, monkeypatch
    ):
        """Test password reset with stdin.

        This tests automation scenario where password is piped in.
        """
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")
        captured_output = io.StringIO()
        new_password = "stdin_newpass123"

        # ACT
        with (
            patch("sys.stdin", io.StringIO(f"{new_password}\n")),
            patch("sys.stdout", captured_output),
        ):
            cmd = AdminResetPassword()
            cmd.run(username="testuser", password_stdin=True)

        # ASSERT
        db_session.expire_all()
        db_session.refresh(sample_user)
        assert sample_user.check_password(new_password)

        output = captured_output.getvalue()
        assert "Password reset successfully" in output

    def test_reset_password_user_not_found(self, db_session: Session, monkeypatch):
        """Test error when user doesn't exist."""
        # ARRANGE
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")

        # ACT + ASSERT
        with (
            patch(
                "hop3.server.cli.admin.getpass.getpass",
                side_effect=["newpass123", "newpass123"],
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd = AdminResetPassword()
            cmd.run(username="nonexistent", password_stdin=False)

        assert exc_info.value.code == 1
