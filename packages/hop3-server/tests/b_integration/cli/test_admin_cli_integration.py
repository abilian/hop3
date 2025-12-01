# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for server-side CLI admin commands.

This module tests admin CLI commands using state-based testing approach:
- Uses real database instead of mocks
- Verifies actual database state changes
- Only mocks external I/O (getpass, stdin, stdout)
- Tests that outcomes (state) are correct, not just that methods were called

See local-notes/test-mock-migration-plan.md for migration strategy.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from hop3.orm import Role, User
from hop3.server.cli.admin import AdminCreate

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
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-token-generation")

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
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")
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

        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

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

        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

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
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key")

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
