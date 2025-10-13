# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for admin user management commands."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from hop3.commands.admin import (
    AdminUserAddCmd,
    AdminUserDisableCmd,
    AdminUserEnableCmd,
    AdminUserGenerateTokenCmd,
    AdminUserGrantAdminCmd,
    AdminUserInfoCmd,
    AdminUserListCmd,
    AdminUserRemoveCmd,
    AdminUserRevokeAdminCmd,
    AdminUserSetPasswordCmd,
)
from hop3.orm import User
from hop3.orm.security import Role


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = Mock(spec=Session)
    return session


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user."""
    user = Mock(spec=User)
    user.username = "admin"
    user.email = "admin@example.com"
    user.is_admin = True
    user.active = True
    user.roles = []
    return user


@pytest.fixture
def mock_regular_user():
    """Create a mock regular user."""
    user = Mock(spec=User)
    user.username = "user"
    user.email = "user@example.com"
    user.is_admin = False
    user.active = True
    user.roles = []
    return user


@pytest.fixture
def mock_admin_role():
    """Create a mock admin role."""
    role = Mock(spec=Role)
    role.name = "admin"
    role.description = "Administrator role"
    return role


def test_admin_user_add_requires_admin(mock_db_session):
    """Test that admin:user:add requires admin privileges."""
    # Mock query to return None (no authenticated user)
    mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

    cmd = AdminUserAddCmd(db_session=mock_db_session)
    result = cmd.call("", "newuser", "new@example.com", "password123")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Authentication required" in result[0]["text"]


def test_admin_user_add_requires_admin_role(mock_db_session, mock_regular_user):
    """Test that admin:user:add requires admin role."""
    # Mock query to return a regular user (not admin)
    mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
        mock_regular_user
    )

    cmd = AdminUserAddCmd(db_session=mock_db_session)
    result = cmd.call("user", "newuser", "new@example.com", "password123")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Admin privileges required" in result[0]["text"]


def test_admin_user_add_missing_arguments(mock_db_session, mock_admin_user):
    """Test that admin:user:add requires username, email, and password."""
    # Mock query to return admin user
    mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
        mock_admin_user
    )

    cmd = AdminUserAddCmd(db_session=mock_db_session)
    result = cmd.call("admin")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Usage:" in result[0]["text"]


def test_admin_user_add_success(mock_db_session, mock_admin_user):
    """Test successful user creation."""
    # Mock the query chain for checking authenticated user, username, and email
    mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
        mock_admin_user,  # Check authenticated user
        None,  # Check existing username
        None,  # Check existing email
    ]

    cmd = AdminUserAddCmd(db_session=mock_db_session)
    result = cmd.call("admin", "newuser", "new@example.com", "password123")

    # Verify user was added to session
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()

    # Check result
    assert len(result) >= 3
    assert "created successfully" in result[0]["text"]


def test_admin_user_add_with_admin_flag(
    mock_db_session, mock_admin_user, mock_admin_role
):
    """Test user creation with admin flag."""
    from unittest.mock import patch

    # Create a mock for the new user that will be created
    mock_new_user = Mock(spec=User)
    mock_new_user.roles = Mock()
    mock_new_user.set_password = Mock()
    mock_new_user.username = "newadmin"
    mock_new_user.email = "admin2@example.com"
    mock_new_user.active = True

    # Mock queries
    mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
        mock_admin_user,  # Check authenticated user
        None,  # Check existing username
        None,  # Check existing email
        mock_admin_role,  # Get admin role
    ]
    mock_db_session.flush = Mock()

    # Patch the User class constructor to return our mock
    with patch("hop3.commands.admin.User", return_value=mock_new_user):
        cmd = AdminUserAddCmd(db_session=mock_db_session)
        result = cmd.call(
            "admin", "newadmin", "admin2@example.com", "password123", "--admin"
        )

    # Verify database operations
    mock_db_session.add.assert_called()
    mock_db_session.commit.assert_called_once()

    # Verify roles.append was called with the admin role
    mock_new_user.roles.append.assert_called_once()

    # Check that admin flag is mentioned in result
    result_text = " ".join(r["text"] for r in result)
    assert "Admin: Yes" in result_text


def test_admin_user_remove_prevents_self_deletion(mock_db_session, mock_admin_user):
    """Test that admin cannot remove their own account."""
    mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
        mock_admin_user
    )

    cmd = AdminUserRemoveCmd(db_session=mock_db_session)
    result = cmd.call("admin", "admin")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Cannot remove your own account" in result[0]["text"]


def test_admin_user_list(mock_db_session, mock_admin_user, mock_regular_user):
    """Test listing users."""
    users = [mock_admin_user, mock_regular_user]
    mock_admin_user.login_count = 5
    mock_regular_user.login_count = 2

    # Setup mock query chain
    mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
        mock_admin_user
    )
    mock_db_session.query.return_value.order_by.return_value.all.return_value = users

    cmd = AdminUserListCmd(db_session=mock_db_session)
    result = cmd.call("admin")

    # Check that both users are listed
    result_text = " ".join(r["text"] for r in result)
    assert "admin" in result_text
    assert "user" in result_text
    assert "Total users: 2" in result_text


def test_admin_user_enable(mock_db_session, mock_admin_user):
    """Test enabling a disabled user."""
    disabled_user = Mock(spec=User)
    disabled_user.username = "disabled"
    disabled_user.active = False

    # First call returns admin, second call returns the disabled user
    mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
        mock_admin_user,
        disabled_user,
    ]

    cmd = AdminUserEnableCmd(db_session=mock_db_session)
    result = cmd.call("admin", "disabled")

    assert disabled_user.active is True
    mock_db_session.commit.assert_called_once()
    assert "enabled successfully" in result[0]["text"]


def test_admin_user_disable_prevents_self_disable(mock_db_session, mock_admin_user):
    """Test that admin cannot disable their own account."""
    mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
        mock_admin_user
    )

    cmd = AdminUserDisableCmd(db_session=mock_db_session)
    result = cmd.call("admin", "admin")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Cannot disable your own account" in result[0]["text"]


def test_admin_user_grant_admin(
    mock_db_session, mock_admin_user, mock_regular_user, mock_admin_role
):
    """Test granting admin privileges."""
    mock_regular_user.roles = Mock()
    mock_regular_user.roles.append = Mock()

    # Create separate mocks for User and Role queries
    user_mock = Mock()
    user_mock.filter_by.return_value.first.side_effect = [
        mock_admin_user,  # Check authenticated user
        mock_regular_user,  # Target user
    ]

    role_mock = Mock()
    role_mock.filter_by.return_value.first.return_value = mock_admin_role

    # Setup query to return different mocks based on model
    def query_side_effect(model):
        if model == User:
            return user_mock
        if model == Role:
            return role_mock
        return Mock()

    mock_db_session.query.side_effect = query_side_effect

    cmd = AdminUserGrantAdminCmd(db_session=mock_db_session)
    result = cmd.call("admin", "user")

    mock_regular_user.roles.append.assert_called_once_with(mock_admin_role)
    mock_db_session.commit.assert_called_once()
    assert "granted" in result[0]["text"]


def test_admin_user_revoke_admin_prevents_self_revocation(
    mock_db_session, mock_admin_user
):
    """Test that admin cannot revoke their own admin privileges."""
    mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
        mock_admin_user
    )

    cmd = AdminUserRevokeAdminCmd(db_session=mock_db_session)
    result = cmd.call("admin", "admin")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Cannot revoke admin privileges from yourself" in result[0]["text"]


def test_admin_user_set_password(mock_db_session, mock_admin_user, mock_regular_user):
    """Test resetting a user's password."""
    # First call returns admin, second call returns the target user
    mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
        mock_admin_user,
        mock_regular_user,
    ]

    cmd = AdminUserSetPasswordCmd(db_session=mock_db_session)
    result = cmd.call("admin", "user", "newpassword123")

    mock_regular_user.set_password.assert_called_once_with("newpassword123")
    mock_db_session.commit.assert_called_once()
    assert "Password reset successfully" in result[0]["text"]


def test_admin_user_info(mock_db_session, mock_admin_user, mock_regular_user):
    """Test displaying user information."""
    mock_regular_user.login_count = 10
    mock_regular_user.current_login_at = datetime.now(timezone.utc)
    mock_regular_user.last_login_at = datetime.now(timezone.utc)
    mock_regular_user.confirmed_at = datetime.now(timezone.utc)
    mock_regular_user.created_at = datetime.now(timezone.utc)
    mock_regular_user.updated_at = datetime.now(timezone.utc)

    # First call returns admin, second call returns the target user
    mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
        mock_admin_user,
        mock_regular_user,
    ]

    cmd = AdminUserInfoCmd(db_session=mock_db_session)
    result = cmd.call("admin", "user")

    result_text = " ".join(r["text"] for r in result)
    assert "User Information" in result_text
    assert "user@example.com" in result_text
    assert "Login count: 10" in result_text


def test_admin_user_generate_token(
    mock_db_session, mock_admin_user, mock_regular_user, monkeypatch
):
    """Test generating a token for a user."""
    # Set the secret key environment variable
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-testing-only")

    # First call returns admin, second call returns the target user
    mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
        mock_admin_user,
        mock_regular_user,
    ]

    cmd = AdminUserGenerateTokenCmd(db_session=mock_db_session)
    result = cmd.call("admin", "user")

    # Check that a token is in the result
    result_text = " ".join(r["text"] for r in result)
    assert "Token:" in result_text
    assert "api_token" in result_text


def test_admin_user_generate_token_disabled_user(mock_db_session, mock_admin_user):
    """Test that token generation fails for disabled users."""
    disabled_user = Mock(spec=User)
    disabled_user.username = "disabled"
    disabled_user.active = False

    # First call returns admin, second call returns the disabled user
    mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
        mock_admin_user,
        disabled_user,
    ]

    cmd = AdminUserGenerateTokenCmd(db_session=mock_db_session)
    result = cmd.call("admin", "disabled")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "disabled" in result[0]["text"]
