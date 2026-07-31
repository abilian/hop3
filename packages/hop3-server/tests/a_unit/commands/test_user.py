# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for user management commands."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from hop3.commands.user import (
    UserAddCmd,
    UserDisableCmd,
    UserEnableCmd,
    UserGenerateTokenCmd,
    UserGrantAdminCmd,
    UserListCmd,
    UserRemoveCmd,
    UserRevokeAdminCmd,
    UserSetPasswordCmd,
    UserShowCmd,
)
from hop3.orm import User
from hop3.orm.repositories import RoleRepository, UserRepository
from hop3.orm.security import Role


@pytest.fixture
def mock_user_repo():
    """Create a mock user repository."""
    repo = Mock(spec=UserRepository)
    return repo


@pytest.fixture
def mock_role_repo():
    """Create a mock role repository."""
    repo = Mock(spec=RoleRepository)
    return repo


@pytest.fixture
def mock_admin_user():
    """Create a mock user."""
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


def test_admin_user_add_requires_admin(mock_user_repo, mock_role_repo):
    """Test that admin:user:add requires admin privileges."""
    # Mock to return None (no authenticated user)
    mock_user_repo.get_by_username.return_value = None

    cmd = UserAddCmd(user_repo=mock_user_repo, role_repo=mock_role_repo)
    result = cmd.call("", "newuser", "new@example.com", "password123")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Authentication required" in result[0]["text"]


def test_admin_user_add_requires_admin_role(
    mock_user_repo, mock_role_repo, mock_regular_user
):
    """Test that admin:user:add requires admin role."""
    # Mock to return a regular user (not admin)
    mock_user_repo.get_by_username.return_value = mock_regular_user

    cmd = UserAddCmd(user_repo=mock_user_repo, role_repo=mock_role_repo)
    result = cmd.call("user", "newuser", "new@example.com", "password123")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Admin privileges required" in result[0]["text"]


def test_admin_user_add_missing_arguments(
    mock_user_repo, mock_role_repo, mock_admin_user
):
    """Test that admin:user:add requires username, email, and password."""
    # Mock to return user
    mock_user_repo.get_by_username.return_value = mock_admin_user

    cmd = UserAddCmd(user_repo=mock_user_repo, role_repo=mock_role_repo)
    result = cmd.call("admin")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Usage:" in result[0]["text"]


def test_admin_user_add_success(mock_user_repo, mock_role_repo, mock_admin_user):
    """Test successful user creation."""
    # Mock the repository methods
    mock_user_repo.get_by_username.return_value = mock_admin_user
    mock_user_repo.username_exists.return_value = False
    mock_user_repo.email_exists.return_value = False

    cmd = UserAddCmd(user_repo=mock_user_repo, role_repo=mock_role_repo)
    result = cmd.call("admin", "newuser", "new@example.com", "password123")

    # Verify user was added to repository
    mock_user_repo.add.assert_called_once()

    # Check result
    assert len(result) >= 3
    assert "created successfully" in result[0]["text"]


def test_user_add_states_the_account_is_operator_equivalent(
    mock_user_repo, mock_role_repo, mock_admin_user
):
    """
    Creating a non-admin account must say it still reaches every app.

    The control plane is single-tenant (no per-app ownership), so "Admin: No"
    would otherwise imply a confinement Hop3 does not provide. See
    notes/security/security-model.md §1.4 and report-2026-07.md finding 1.
    """
    mock_user_repo.get_by_username.return_value = mock_admin_user
    mock_user_repo.username_exists.return_value = False
    mock_user_repo.email_exists.return_value = False

    cmd = UserAddCmd(user_repo=mock_user_repo, role_repo=mock_role_repo)
    result = cmd.call("admin", "newuser", "new@example.com", "password123")

    notice = " ".join(item.get("text", "") for item in result)
    assert "every app and addon" in notice
    assert "no per-app ownership" in notice.lower()


# user:add with --admin is covered by
# b_integration/commands/test_user_commands_integration.py::test_add_user_with_admin_flag
# (real in-memory DB; asserts user.is_admin is True).


def test_admin_user_remove_prevents_self_deletion(mock_user_repo, mock_admin_user):
    """Test that admin cannot remove their own account."""
    mock_user_repo.get_by_username.return_value = mock_admin_user

    cmd = UserRemoveCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "admin")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Cannot remove your own account" in result[0]["text"]


def test_admin_user_list(mock_user_repo, mock_admin_user, mock_regular_user):
    """Test listing users."""
    users = [mock_admin_user, mock_regular_user]
    mock_admin_user.login_count = 5
    mock_regular_user.login_count = 2

    # Setup mock repository
    mock_user_repo.get_by_username.return_value = mock_admin_user
    mock_user_repo.list_all_ordered.return_value = users

    cmd = UserListCmd(user_repo=mock_user_repo)
    result = cmd.call("admin")

    # Check that both users are listed
    result_text = " ".join(r["text"] for r in result)
    assert "admin" in result_text
    assert "user" in result_text
    assert "Total users: 2" in result_text


def test_admin_user_enable(mock_user_repo, mock_admin_user):
    """Test enabling a disabled user."""
    disabled_user = Mock(spec=User)
    disabled_user.username = "disabled"
    disabled_user.active = False

    # First call returns admin, second call returns the disabled user
    mock_user_repo.get_by_username.side_effect = [mock_admin_user, disabled_user]

    cmd = UserEnableCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "disabled")

    assert disabled_user.active is True
    mock_user_repo.update.assert_called_once()
    assert "enabled successfully" in result[0]["text"]


def test_admin_user_disable_prevents_self_disable(mock_user_repo, mock_admin_user):
    """Test that admin cannot disable their own account."""
    mock_user_repo.get_by_username.return_value = mock_admin_user

    cmd = UserDisableCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "admin")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Cannot disable your own account" in result[0]["text"]


def test_admin_user_grant_admin(
    mock_user_repo, mock_role_repo, mock_admin_user, mock_regular_user, mock_admin_role
):
    """Test granting admin privileges."""
    mock_regular_user.roles = Mock()
    mock_regular_user.roles.append = Mock()
    mock_regular_user.is_admin = False  # Not admin initially

    # Mock repository methods for sequential calls
    mock_user_repo.get_by_username.side_effect = [mock_admin_user, mock_regular_user]
    mock_role_repo.get_admin_role.return_value = mock_admin_role

    cmd = UserGrantAdminCmd(user_repo=mock_user_repo, role_repo=mock_role_repo)
    result = cmd.call("admin", "user")

    mock_regular_user.roles.append.assert_called_once_with(mock_admin_role)
    mock_user_repo.update.assert_called_once()
    assert "granted" in result[0]["text"]


def test_admin_user_revoke_admin_prevents_self_revocation(
    mock_user_repo, mock_role_repo, mock_admin_user
):
    """Test that admin cannot revoke their own admin privileges."""
    mock_user_repo.get_by_username.return_value = mock_admin_user

    cmd = UserRevokeAdminCmd(user_repo=mock_user_repo, role_repo=mock_role_repo)
    result = cmd.call("admin", "admin")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Cannot revoke admin privileges from yourself" in result[0]["text"]


def test_admin_user_set_password(mock_user_repo, mock_admin_user, mock_regular_user):
    """Test resetting a user's password."""
    # First call returns admin, second call returns the target user
    mock_user_repo.get_by_username.side_effect = [mock_admin_user, mock_regular_user]

    cmd = UserSetPasswordCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "user", "newpassword123")

    mock_regular_user.set_password.assert_called_once_with("newpassword123")
    mock_user_repo.update.assert_called_once()
    assert "Password reset successfully" in result[0]["text"]


def test_admin_user_info(mock_user_repo, mock_admin_user, mock_regular_user):
    """Test displaying user information."""
    mock_regular_user.login_count = 10
    mock_regular_user.current_login_at = datetime.now(timezone.utc)
    mock_regular_user.last_login_at = datetime.now(timezone.utc)
    mock_regular_user.confirmed_at = datetime.now(timezone.utc)
    mock_regular_user.created_at = datetime.now(timezone.utc)
    mock_regular_user.updated_at = datetime.now(timezone.utc)

    # First call returns admin, second call returns the target user
    mock_user_repo.get_by_username.side_effect = [mock_admin_user, mock_regular_user]

    cmd = UserShowCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "user")

    result_text = " ".join(r["text"] for r in result)
    assert "User Information" in result_text
    assert "user@example.com" in result_text
    assert "Login count: 10" in result_text


def test_admin_user_generate_token(
    mock_user_repo, mock_admin_user, mock_regular_user, monkeypatch
):
    """Test generating a token for a user."""
    # Set the secret key environment variable
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-testing-only")

    # First call returns admin, second call returns the target user
    mock_user_repo.get_by_username.side_effect = [mock_admin_user, mock_regular_user]

    cmd = UserGenerateTokenCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "user")

    # Check that a token is in the result
    result_text = " ".join(r["text"] for r in result)
    assert "Token:" in result_text
    assert "api_token" in result_text


def test_admin_user_generate_token_disabled_user(mock_user_repo, mock_admin_user):
    """Test that token generation fails for disabled users."""
    disabled_user = Mock(spec=User)
    disabled_user.username = "disabled"
    disabled_user.active = False

    # First call returns admin, second call returns the disabled user
    mock_user_repo.get_by_username.side_effect = [mock_admin_user, disabled_user]

    cmd = UserGenerateTokenCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "disabled")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "disabled" in result[0]["text"]
