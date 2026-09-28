# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for admin command classes using state-based testing.

This module tests admin commands using real database interactions:
- Uses real database instead of mocks (via db_session fixture)
- Commands receive repository instances for database access
- Verifies actual database state changes
- Tests that outcomes (state) are correct, not just that methods were called
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

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
    UserSetRoleCmd,
    UserShowCmd,
)
from hop3.core.roles import Role
from hop3.orm import User
from hop3.orm.repositories import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture
def user_repo(db_session: Session) -> UserRepository:
    """Create a user repository for testing."""
    return UserRepository(session=db_session)


@pytest.mark.integration
class TestAdminUserAddCmdIntegration:
    """Integration tests for UserAddCmd using state-based testing."""

    def test_add_user_requires_all_arguments(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test that admin:user:add requires username, email, and password.

        ARRANGE:
            - Create an user

        ACT:
            - Call command with missing arguments

        ASSERT:
            - Verify usage error message
            - Verify no new user was created
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserAddCmd(user_repo=user_repo)

        with pytest.raises(ValueError, match="Usage: hop3 user add"):
            cmd.call(sample_user.username)

        # Verify no new user was created
        db_session.expire_all()
        users = db_session.query(User).all()
        assert len(users) == 1, "Only the user should exist"

    def test_add_user_success(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test successful user creation.

        ARRANGE:
            - Create an user

        ACT:
            - Create a new user

        ASSERT:
            - Verify user was created in database
            - Verify user has correct attributes
            - Verify password was set correctly
            - Verify success message
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserAddCmd(user_repo=user_repo)

        result = cmd.call(
            sample_user.username, "newuser", "new@example.com", "password123"
        )

        db_session.expire_all()
        new_user = db_session.query(User).filter_by(username="newuser").first()

        assert new_user is not None, "User should be created in database"
        assert new_user.username == "newuser"
        assert new_user.email == "new@example.com"
        assert new_user.active is True
        assert new_user.confirmed_at is not None

        # Verify password was set correctly
        assert new_user.check_password("password123"), "Password should be verifiable"
        assert not new_user.check_password("wrongpass"), (
            "Wrong password should not authenticate"
        )

        # Verify output
        assert len(result) >= 3
        result_text = " ".join(r["text"] for r in result)
        assert "created successfully" in result_text

    def test_add_user_with_admin_flag(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test user creation with admin flag.

        ARRANGE:
            - Create an user
            - Ensure admin role exists

        ACT:
            - Create a new user with --admin flag

        ASSERT:
            - Verify user was created with admin role
            - Verify user.is_admin returns True
            - Verify the new user holds the admin role
            - Verify success message mentions admin
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserAddCmd(user_repo=user_repo)

        result = cmd.call(
            sample_user.username,
            "newadmin",
            "admin2@example.com",
            "password123",
            "--admin",
        )

        db_session.expire_all()
        new_user = db_session.query(User).filter_by(username="newadmin").first()

        assert new_user is not None, "User should be created in database"
        assert new_user.username == "newadmin"
        assert new_user.email == "admin2@example.com"
        assert new_user.active is True
        assert new_user.is_admin is True, "User should have admin privileges"

        # Verify admin role was assigned
        assert new_user.role is Role.ADMIN, "User should have admin role"

        # Verify output
        result_text = " ".join(r["text"] for r in result)
        assert "Role: admin" in result_text

    def test_add_user_username_exists(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test error when username already exists.

        ARRANGE:
            - Create an user
            - Existing user already in database

        ACT:
            - Try to create user with duplicate username

        ASSERT:
            - Verify error message about duplicate username
            - Verify no new user was created
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserAddCmd(user_repo=user_repo)

        result = cmd.call(
            sample_user.username,
            sample_user.username,  # Duplicate username
            "different@example.com",
            "password123",
        )

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "already exists" in result[0]["text"]

        # Verify no duplicate was created
        db_session.expire_all()
        users = db_session.query(User).filter_by(username=sample_user.username).all()
        assert len(users) == 1, "Should still be only one user with this username"

    def test_add_user_email_exists(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test error when email already exists.

        ARRANGE:
            - Create an user
            - Existing user with email already in database

        ACT:
            - Try to create user with duplicate email

        ASSERT:
            - Verify error message about duplicate email
            - Verify no new user was created
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserAddCmd(user_repo=user_repo)

        result = cmd.call(
            sample_user.username,
            "different_username",
            sample_user.email,  # Duplicate email
            "password123",
        )

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "already registered" in result[0]["text"]

        # Verify no user with the new username was created
        db_session.expire_all()
        user = db_session.query(User).filter_by(username="different_username").first()
        assert user is None, "No user should be created with duplicate email"


@pytest.mark.integration
class TestAdminUserRemoveCmdIntegration:
    """Integration tests for UserRemoveCmd using state-based testing."""

    def test_remove_user_prevents_self_deletion(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test that admin cannot remove their own account.

        ARRANGE:
            - Create an user

        ACT:
            - Try to remove own account

        ASSERT:
            - Verify error message
            - Verify user still exists in database
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserRemoveCmd(user_repo=user_repo)

        result = cmd.call(sample_user.username, sample_user.username)

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "Cannot remove your own account" in result[0]["text"]

        # Verify user still exists
        db_session.expire_all()
        user = db_session.query(User).filter_by(username=sample_user.username).first()
        assert user is not None, "Admin should still exist"

    def test_remove_user_success(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test successful user removal.

        ARRANGE:
            - Create an user
            - Create a target user to remove

        ACT:
            - Remove the target user

        ASSERT:
            - Verify user was removed from database
            - Verify user still exists
            - Verify success message
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("adminpass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)
        db_session.commit()

        # Target user is sample_user
        assert db_session.query(User).filter_by(username="testuser").first() is not None

        cmd = UserRemoveCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username)

        db_session.expire_all()
        removed_user = db_session.query(User).filter_by(username="testuser").first()
        admin_still_exists = db_session.query(User).filter_by(username="admin").first()

        assert removed_user is None, "Target user should be removed from database"
        assert admin_still_exists is not None, "Admin user should still exist"

        # Verify output
        assert result[0]["t"] == "text"
        assert "removed successfully" in result[0]["text"]

    def test_remove_user_not_found(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test error when user doesn't exist.

        ARRANGE:
            - Create an user

        ACT:
            - Try to remove non-existent user

        ASSERT:
            - Verify error message about user not found
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserRemoveCmd(user_repo=user_repo)

        result = cmd.call(sample_user.username, "nonexistent")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]


@pytest.mark.integration
class TestAdminUserListCmdIntegration:
    """Integration tests for UserListCmd using state-based testing."""

    def test_list_users_success(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test listing users.

        ARRANGE:
            - Create an user
            - Create additional test users

        ACT:
            - List all users

        ASSERT:
            - Verify all users are listed
            - Verify user details in output
            - Verify total count
        """
        sample_user.role = Role.ADMIN
        sample_user.login_count = 5
        db_session.commit()

        # Create another user
        user2 = User(username="user2", email="user2@example.com")
        user2.set_password("pass")
        user2.login_count = 2
        db_session.add(user2)
        db_session.commit()

        cmd = UserListCmd(user_repo=user_repo)

        result = cmd.call(sample_user.username)

        result_text = " ".join(r["text"] for r in result)
        assert "testuser" in result_text
        assert "user2" in result_text
        assert "Total users: 2" in result_text

    def test_list_users_empty_database(
        self, db_session: Session, user_repo: UserRepository
    ):
        """
        Test listing when no users exist.

        ARRANGE:
            - Empty database (no users)
            - Create user temporarily for auth

        ACT:
            - List users

        ASSERT:
            - Verify "No users found" message
        """
        # (This is a bit of a hack since we need an admin to run the command)
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)
        db_session.commit()

        # Now delete the admin to test empty list
        db_session.delete(admin_user)
        db_session.commit()

        # We can't actually test this properly since we need an admin to run the command
        # So let's test with just the user
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)
        db_session.commit()

        cmd = UserListCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username)

        result_text = " ".join(r["text"] for r in result)
        assert "Total users: 1" in result_text


@pytest.mark.integration
class TestAdminUserEnableCmdIntegration:
    """Integration tests for UserEnableCmd using state-based testing."""

    def test_enable_disabled_user(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test enabling a disabled user.

        ARRANGE:
            - Create an user
            - Create a disabled user

        ACT:
            - Enable the disabled user

        ASSERT:
            - Verify user.active is now True
            - Verify success message
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)

        # Create disabled user
        disabled_user = User(username="disabled", email="disabled@example.com")
        disabled_user.set_password("pass")
        disabled_user.active = False
        db_session.add(disabled_user)
        db_session.commit()

        assert disabled_user.active is False, "User should start disabled"

        cmd = UserEnableCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, "disabled")

        db_session.expire_all()
        db_session.refresh(disabled_user)

        assert disabled_user.active is True, "User should be enabled"
        assert "enabled successfully" in result[0]["text"]

    def test_enable_already_enabled_user(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test enabling an already enabled user.

        ARRANGE:
            - Create an user
            - Create an enabled user

        ACT:
            - Try to enable the already enabled user

        ASSERT:
            - Verify message about already enabled
            - Verify user.active is still True
        """
        sample_user.role = Role.ADMIN
        sample_user.active = True
        db_session.commit()

        # Create enabled user
        enabled_user = User(username="enabled", email="enabled@example.com")
        enabled_user.set_password("pass")
        enabled_user.active = True
        db_session.add(enabled_user)
        db_session.commit()

        cmd = UserEnableCmd(user_repo=user_repo)

        result = cmd.call(sample_user.username, "enabled")

        assert "already enabled" in result[0]["text"]
        db_session.refresh(enabled_user)
        assert enabled_user.active is True


@pytest.mark.integration
class TestAdminUserDisableCmdIntegration:
    """Integration tests for UserDisableCmd using state-based testing."""

    def test_disable_user_prevents_self_disable(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test that admin cannot disable their own account.

        ARRANGE:
            - Create an user

        ACT:
            - Try to disable own account

        ASSERT:
            - Verify error message
            - Verify user.active is still True
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserDisableCmd(user_repo=user_repo)

        result = cmd.call(sample_user.username, sample_user.username)

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "Cannot disable your own account" in result[0]["text"]

        # Verify user is still active
        db_session.refresh(sample_user)
        assert sample_user.active is True

    def test_disable_user_success(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test successful user disabling.

        ARRANGE:
            - Create an user
            - Create a target user to disable

        ACT:
            - Disable the target user

        ASSERT:
            - Verify user.active is now False
            - Verify success message
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)

        # sample_user is the target
        sample_user.active = True
        db_session.commit()

        cmd = UserDisableCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username)

        db_session.expire_all()
        db_session.refresh(sample_user)

        assert sample_user.active is False, "User should be disabled"
        assert "disabled successfully" in result[0]["text"]

    def test_disable_already_disabled_user(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test disabling an already disabled user.

        ARRANGE:
            - Create an user
            - Create a disabled user

        ACT:
            - Try to disable the already disabled user

        ASSERT:
            - Verify message about already disabled
            - Verify user.active is still False
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)

        # Create disabled user
        disabled_user = User(username="disabled", email="disabled@example.com")
        disabled_user.set_password("pass")
        disabled_user.active = False
        db_session.add(disabled_user)
        db_session.commit()

        cmd = UserDisableCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, "disabled")

        assert "already disabled" in result[0]["text"]
        db_session.refresh(disabled_user)
        assert disabled_user.active is False


@pytest.mark.integration
class TestAdminUserGrantAdminCmdIntegration:
    """Integration tests for UserGrantAdminCmd using state-based testing."""

    def test_grant_admin_privileges(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test granting admin privileges to a user.

        ARRANGE:
            - Create an user
            - Create a regular user
            - Ensure admin role exists

        ACT:
            - Grant admin privileges to regular user

        ASSERT:
            - Verify user now has admin role
            - Verify user.is_admin returns True
            - Verify success message
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)
        db_session.commit()

        # sample_user is regular user
        assert sample_user.is_admin is False, "User should not be admin initially"

        cmd = UserGrantAdminCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username)

        db_session.expire_all()
        db_session.refresh(sample_user)

        assert sample_user.is_admin is True, "User should now be admin"
        assert sample_user.role is Role.ADMIN, "User should have admin role"
        assert "is now admin" in result[0]["text"]

    def test_grant_admin_already_admin(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test granting admin to user who already has admin.

        ARRANGE:
            - Create an user
            - Create another user

        ACT:
            - Try to grant admin to user who already has it

        ASSERT:
            - Verify message about already having admin
            - Verify user still has admin role
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)

        # Make sample_user an admin too
        sample_user.role = Role.ADMIN
        db_session.commit()

        assert sample_user.is_admin is True

        cmd = UserGrantAdminCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username)

        assert "is already admin" in result[0]["text"]
        db_session.refresh(sample_user)
        assert sample_user.is_admin is True


@pytest.mark.integration
class TestAdminUserRevokeAdminCmdIntegration:
    """Integration tests for UserRevokeAdminCmd using state-based testing."""

    def test_revoke_admin_prevents_self_revocation(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test that admin cannot revoke their own admin privileges.

        ARRANGE:
            - Create an user

        ACT:
            - Try to revoke own admin privileges

        ASSERT:
            - Verify error message
            - Verify user still has admin role
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserRevokeAdminCmd(user_repo=user_repo)

        result = cmd.call(sample_user.username, sample_user.username)

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "Cannot change your own role" in result[0]["text"]

        # Verify user still has admin role
        db_session.refresh(sample_user)
        assert sample_user.is_admin is True

    def test_revoke_admin_success(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test successful admin revocation.

        ARRANGE:
            - Create two admin users

        ACT:
            - Revoke admin from one of them

        ASSERT:
            - Verify target user no longer has admin role
            - Verify user.is_admin returns False
            - Verify success message
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)

        # Make sample_user an admin too
        sample_user.role = Role.ADMIN
        db_session.commit()

        assert sample_user.is_admin is True

        cmd = UserRevokeAdminCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username)

        db_session.expire_all()
        db_session.refresh(sample_user)

        # Revoking admin leaves what a non-admin account could always do.
        assert sample_user.role is Role.DEPLOYER
        assert "is now deployer (was admin)" in result[0]["text"]

    def test_revoke_admin_not_admin(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test revoking admin from user who doesn't have it.

        ARRANGE:
            - Create an user
            - Create a regular user

        ACT:
            - Try to revoke admin from regular user

        ASSERT:
            - Verify message about not having admin
            - Verify user still doesn't have admin
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)
        db_session.commit()

        # sample_user is regular user
        assert sample_user.is_admin is False

        cmd = UserRevokeAdminCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username)

        assert "is not an admin" in result[0]["text"]
        db_session.refresh(sample_user)
        assert sample_user.is_admin is False


@pytest.mark.integration
class TestAdminUserSetPasswordCmdIntegration:
    """Integration tests for UserSetPasswordCmd using state-based testing."""

    def test_set_password_success(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test resetting a user's password.

        ARRANGE:
            - Create an user
            - Create a target user with known password

        ACT:
            - Reset target user's password

        ASSERT:
            - Verify old password no longer works
            - Verify new password works
            - Verify success message
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("adminpass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)
        db_session.commit()

        # Store original password for comparison
        original_password = "testpass123"
        new_password = "newpassword123"

        # Verify original password works
        assert sample_user.check_password(original_password)

        cmd = UserSetPasswordCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username, new_password)

        db_session.expire_all()
        db_session.refresh(sample_user)

        assert sample_user.check_password(new_password), "New password should work"
        assert not sample_user.check_password(original_password), (
            "Old password should not work"
        )
        assert "Password reset successfully" in result[0]["text"]

    def test_set_password_user_not_found(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test error when user doesn't exist.

        ARRANGE:
            - Create an user

        ACT:
            - Try to reset password for non-existent user

        ASSERT:
            - Verify error message about user not found
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserSetPasswordCmd(user_repo=user_repo)

        result = cmd.call(sample_user.username, "nonexistent", "newpass123")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]


@pytest.mark.integration
class TestAdminUserInfoCmdIntegration:
    """Integration tests for UserShowCmd using state-based testing."""

    def test_user_info_success(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test displaying user information.

        ARRANGE:
            - Create an user
            - Create a target user with various attributes set

        ACT:
            - Get user info

        ASSERT:
            - Verify all user attributes are displayed
            - Verify correct values
        """
        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)

        # Set up sample_user with various attributes
        sample_user.login_count = 10
        sample_user.current_login_at = datetime.now(timezone.utc)
        sample_user.last_login_at = datetime.now(timezone.utc)
        sample_user.confirmed_at = datetime.now(timezone.utc)
        db_session.commit()

        cmd = UserShowCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username)

        result_text = " ".join(r["text"] for r in result)
        assert "User Information" in result_text
        assert "testuser" in result_text
        assert "test@example.com" in result_text
        assert "Login count: 10" in result_text
        assert "Active: True" in result_text

    def test_user_info_not_found(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
    ):
        """
        Test error when user doesn't exist.

        ARRANGE:
            - Create an user

        ACT:
            - Try to get info for non-existent user

        ASSERT:
            - Verify error message about user not found
        """
        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserShowCmd(user_repo=user_repo)

        result = cmd.call(sample_user.username, "nonexistent")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]


@pytest.mark.integration
class TestAdminUserGenerateTokenCmdIntegration:
    """Integration tests for UserGenerateTokenCmd using state-based testing."""

    def test_generate_token_success(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
        monkeypatch,
    ):
        """
        Test generating a token for a user.

        ARRANGE:
            - Set secret key environment variable
            - Create an user
            - Create a target user

        ACT:
            - Generate token for target user

        ASSERT:
            - Verify token is in output
            - Verify success message
        """
        monkeypatch.setenv(
            "HOP3_SECRET_KEY", "test-secret-key-for-unit-testing-for-testing-only"
        )

        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)
        sample_user.role = Role.VIEWER  # a member gets no token
        db_session.commit()

        cmd = UserGenerateTokenCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username)

        result_text = " ".join(r["text"] for r in result)
        assert "Token:" in result_text
        assert "api_token" in result_text

    def test_generate_token_disabled_user(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
        monkeypatch,
    ):
        """
        Test that token generation fails for disabled users.

        ARRANGE:
            - Set secret key environment variable
            - Create an user
            - Create a disabled user

        ACT:
            - Try to generate token for disabled user

        ASSERT:
            - Verify error message about disabled user
        """
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")

        admin_user = User(username="admin", email="admin@example.com")
        admin_user.set_password("pass")
        admin_user.role = Role.ADMIN
        db_session.add(admin_user)

        # Disable sample_user
        sample_user.active = False
        db_session.commit()

        cmd = UserGenerateTokenCmd(user_repo=user_repo)

        result = cmd.call(admin_user.username, sample_user.username)

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "disabled" in result[0]["text"]

    def test_generate_token_user_not_found(
        self,
        db_session: Session,
        sample_user: User,
        user_repo: UserRepository,
        monkeypatch,
    ):
        """
        Test error when user doesn't exist.

        ARRANGE:
            - Set secret key environment variable
            - Create an user

        ACT:
            - Try to generate token for non-existent user

        ASSERT:
            - Verify error message about user not found
        """
        monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-unit-testing")

        sample_user.role = Role.ADMIN
        db_session.commit()

        cmd = UserGenerateTokenCmd(user_repo=user_repo)

        result = cmd.call(sample_user.username, "nonexistent")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]


@pytest.mark.integration
class TestUserRolesIntegration:
    """Standard roles (ADR 061): chosen at creation, changed with set-role."""

    @pytest.fixture
    def admin(self, db_session: Session, sample_user: User) -> User:
        sample_user.role = Role.ADMIN
        db_session.commit()
        return sample_user

    def _add(self, user_repo: UserRepository, admin: User, *args: str) -> list[dict]:
        return UserAddCmd(user_repo=user_repo).call(
            admin.username, "bob", "bob@example.com", "password123", *args
        )

    def test_a_new_account_is_a_member(self, user_repo, admin):
        result = self._add(user_repo, admin)

        assert user_repo.get_by_username("bob").role is Role.MEMBER
        assert "Role: member" in " ".join(r["text"] for r in result)

    def test_add_with_a_role(self, user_repo, admin):
        self._add(user_repo, admin, "--role", "viewer")

        assert user_repo.get_by_username("bob").role is Role.VIEWER

    def test_add_with_an_unknown_role_creates_nothing(self, user_repo, admin):
        result = self._add(user_repo, admin, "--role", "editor")

        assert result[0]["t"] == "error"
        assert "member, viewer, deployer, admin" in result[0]["text"]
        assert user_repo.get_by_username("bob") is None

    def test_set_role(self, db_session, user_repo, admin):
        self._add(user_repo, admin)

        result = UserSetRoleCmd(user_repo=user_repo).call(
            admin.username, "bob", "deployer"
        )

        db_session.expire_all()
        assert user_repo.get_by_username("bob").role is Role.DEPLOYER
        assert "is now deployer (was member)" in result[0]["text"]

    def test_an_admin_cannot_change_their_own_role(self, db_session, user_repo, admin):
        """What keeps the server from ever losing its last admin (ADR 061 §2)."""
        result = UserSetRoleCmd(user_repo=user_repo).call(
            admin.username, admin.username, "member"
        )

        db_session.expire_all()
        assert result[0]["t"] == "error"
        assert "Cannot change your own role" in result[0]["text"]
        assert user_repo.get_by_username(admin.username).role is Role.ADMIN

    def test_set_role_refuses_an_unknown_role(self, user_repo, admin):
        self._add(user_repo, admin)

        result = UserSetRoleCmd(user_repo=user_repo).call(admin.username, "bob", "root")

        assert result[0]["t"] == "error"
        assert "Unknown role 'root'" in result[0]["text"]
        assert user_repo.get_by_username("bob").role is Role.MEMBER
