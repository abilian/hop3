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
from hop3.core.roles import Role
from hop3.orm import User
from hop3.orm.repositories import UserRepository


@pytest.fixture
def mock_user_repo():
    """Create a mock user repository."""
    repo = Mock(spec=UserRepository)
    return repo


@pytest.fixture
def mock_admin_user():
    """Create a mock user."""
    user = Mock(spec=User)
    user.username = "admin"
    user.email = "admin@example.com"
    user.is_admin = True
    user.active = True
    user.role = Role.ADMIN
    return user


@pytest.fixture
def mock_regular_user():
    """Create a mock regular user."""
    user = Mock(spec=User)
    user.username = "user"
    user.email = "user@example.com"
    user.is_admin = False
    user.active = True
    user.role = Role.MEMBER
    return user


def test_admin_user_add_missing_arguments(mock_user_repo, mock_admin_user):
    """Test that admin:user:add requires username, email, and password."""
    # Mock to return user
    mock_user_repo.get_by_username.return_value = mock_admin_user

    cmd = UserAddCmd(user_repo=mock_user_repo)
    with pytest.raises(ValueError, match="Usage: hop3 user add"):
        cmd.call("admin")


def test_admin_user_add_success(mock_user_repo, mock_admin_user):
    """Test successful user creation."""
    # Mock the repository methods
    mock_user_repo.get_by_username.return_value = mock_admin_user
    mock_user_repo.username_exists.return_value = False
    mock_user_repo.email_exists.return_value = False

    cmd = UserAddCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "newuser", "new@example.com", "password123")

    # Verify user was added to repository
    mock_user_repo.add.assert_called_once()

    # Check result
    assert len(result) >= 3
    assert "created successfully" in result[0]["text"]


@pytest.mark.parametrize(("role", "noted"), [("deployer", True), ("viewer", False)])
def test_user_add_says_a_deployer_is_an_admin_credential(
    mock_user_repo, mock_admin_user, role, noted
):
    """
    A deployer's builds run with the control plane's privileges (ADR 061 §6).

    Until builds drop to the app user, "deployer" must not read as a
    confinement: the account is created with a note saying so. A viewer runs
    no build, so its role means what it says.
    """
    mock_user_repo.get_by_username.return_value = mock_admin_user
    mock_user_repo.username_exists.return_value = False
    mock_user_repo.email_exists.return_value = False

    cmd = UserAddCmd(user_repo=mock_user_repo)
    result = cmd.call(
        "admin", "newuser", "new@example.com", "password123", "--role", role
    )

    notice = " ".join(item.get("text", "") for item in result)
    assert ("treat this account as an administrator credential" in notice) is noted


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

    mock_user_repo.get_by_username.return_value = disabled_user

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


def test_admin_user_grant_admin(mock_user_repo, mock_admin_user, mock_regular_user):
    """Granting admin sets the role; nothing else is created."""
    mock_user_repo.get_by_username.return_value = mock_regular_user

    cmd = UserGrantAdminCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "user")

    assert mock_regular_user.role is Role.ADMIN
    mock_user_repo.update.assert_called_once()
    assert "is now admin (was member)" in result[0]["text"]


def test_admin_user_revoke_admin_prevents_self_revocation(
    mock_user_repo, mock_admin_user
):
    """Test that admin cannot revoke their own admin privileges."""
    mock_user_repo.get_by_username.return_value = mock_admin_user

    cmd = UserRevokeAdminCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "admin")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "Cannot change your own role" in result[0]["text"]


def test_admin_user_set_password(mock_user_repo, mock_admin_user, mock_regular_user):
    """Test resetting a user's password."""
    mock_user_repo.get_by_username.return_value = mock_regular_user

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

    mock_user_repo.get_by_username.return_value = mock_regular_user

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

    mock_regular_user.role = Role.VIEWER
    mock_user_repo.get_by_username.return_value = mock_regular_user

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

    mock_user_repo.get_by_username.return_value = disabled_user

    cmd = UserGenerateTokenCmd(user_repo=mock_user_repo)
    result = cmd.call("admin", "disabled")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "disabled" in result[0]["text"]


def test_no_token_is_generated_for_a_member(mock_user_repo, mock_regular_user):
    """A member runs no command, so a token for it could do nothing (ADR 061)."""
    mock_user_repo.get_by_username.return_value = mock_regular_user

    result = UserGenerateTokenCmd(user_repo=mock_user_repo).call("admin", "user")

    assert result[0]["t"] == "error"
    assert "is a member" in result[0]["text"]
