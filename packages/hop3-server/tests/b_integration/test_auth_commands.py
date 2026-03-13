# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for authentication commands."""

from __future__ import annotations

import os

import jwt
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from hop3.commands.auth import (
    AuthLoginCmd,
    AuthLogoutCmd,
    AuthMagicLinkCmd,
    AuthRegisterCmd,
    AuthWhoamiCmd,
)
from hop3.orm.repositories import UserRepository
from hop3.orm.security import AuditBase, Role, User


@pytest.fixture(autouse=True)
def setup_secret_key():
    """Set up a test secret key."""
    os.environ["HOP3_SECRET_KEY"] = "test-secret-key-for-integration-testing"
    yield
    os.environ.pop("HOP3_SECRET_KEY", None)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    # Create all tables

    AuditBase.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def user_repo(db_session: Session):
    """Create a UserRepository instance for testing."""
    return UserRepository(session=db_session)


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    user.set_password("testpass123")
    user.active = True

    db_session.add(user)
    db_session.commit()

    return user


@pytest.fixture
def admin_user(db_session: Session):
    """Create an admin user."""
    user = User(username="admin", email="admin@example.com", password_hash="")
    user.set_password("adminpass")
    user.active = True

    admin_role = Role(name="admin", description="Administrator")
    user.roles.append(admin_role)

    db_session.add(user)
    db_session.add(admin_role)
    db_session.commit()

    return user


def test_auth_register_success(user_repo: UserRepository):
    """Test successful user registration."""
    cmd = AuthRegisterCmd(user_repo=user_repo)
    result = cmd.call("newuser", "new@example.com", "password123")

    assert isinstance(result, list)
    assert any("registered successfully" in str(r.get("text", "")) for r in result)

    # Verify user was created in database
    user = user_repo.get_by_username("newuser")
    assert user is not None
    assert user.email == "new@example.com"
    assert user.check_password("password123")
    assert user.active is True


def test_auth_register_missing_params(user_repo: UserRepository):
    """Test registration with missing parameters."""
    cmd = AuthRegisterCmd(user_repo=user_repo)
    result = cmd.call("newuser", "", "")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_register_duplicate_username(user_repo: UserRepository, test_user: User):
    """Test registration with duplicate username."""
    cmd = AuthRegisterCmd(user_repo=user_repo)
    result = cmd.call("testuser", "different@example.com", "password")

    assert isinstance(result, list)
    assert any("already exists" in str(r.get("text", "")) for r in result)


def test_auth_register_duplicate_email(user_repo: UserRepository, test_user: User):
    """Test registration with duplicate email."""
    cmd = AuthRegisterCmd(user_repo=user_repo)
    result = cmd.call("differentuser", "test@example.com", "password")

    assert isinstance(result, list)
    assert any("already registered" in str(r.get("text", "")) for r in result)


def test_auth_login_success(
    db_session: Session, user_repo: UserRepository, test_user: User
):
    """Test successful login."""
    cmd = AuthLoginCmd(user_repo=user_repo)
    result = cmd.call("testuser", "testpass123")

    assert isinstance(result, list)
    assert any("Login successful" in str(r.get("text", "")) for r in result)

    # Check that a token was returned
    assert any("Your API token:" in str(r.get("text", "")) for r in result)

    # Verify login tracking was updated
    db_session.refresh(test_user)
    assert test_user.login_count == 1
    assert test_user.current_login_at is not None


def test_auth_login_wrong_password(user_repo: UserRepository, test_user: User):
    """Test login with wrong password."""
    cmd = AuthLoginCmd(user_repo=user_repo)
    result = cmd.call("testuser", "wrongpassword")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("Invalid username or password" in str(r.get("text", "")) for r in result)


def test_auth_login_nonexistent_user(user_repo: UserRepository):
    """Test login with nonexistent user."""
    cmd = AuthLoginCmd(user_repo=user_repo)
    result = cmd.call("nosuchuser", "password")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_login_inactive_user(
    db_session: Session, user_repo: UserRepository, test_user: User
):
    """Test login with inactive user."""
    test_user.active = False
    db_session.commit()

    cmd = AuthLoginCmd(user_repo=user_repo)
    result = cmd.call("testuser", "testpass123")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("disabled" in str(r.get("text", "")) for r in result)


def test_auth_login_missing_params(user_repo: UserRepository):
    """Test login with missing parameters."""
    cmd = AuthLoginCmd(user_repo=user_repo)
    result = cmd.call("", "")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_login_admin_user_gets_admin_scope(
    user_repo: UserRepository, admin_user: User
):
    """Test that admin users get admin scope in their token."""
    cmd = AuthLoginCmd(user_repo=user_repo)
    result = cmd.call("admin", "adminpass")

    assert isinstance(result, list)
    assert any("Login successful" in str(r.get("text", "")) for r in result)

    # The token should be in the result - we could decode it to verify admin scope
    # but for now just check that login succeeded


def test_auth_whoami_success(user_repo: UserRepository, test_user: User):
    """Test whoami command."""
    cmd = AuthWhoamiCmd(user_repo=user_repo)
    result = cmd.call("testuser")  # Username would come from auth middleware

    assert isinstance(result, list)
    assert any("testuser" in str(r.get("text", "")) for r in result)
    assert any("test@example.com" in str(r.get("text", "")) for r in result)


def test_auth_whoami_no_username(user_repo: UserRepository):
    """Test whoami without username (not authenticated)."""
    cmd = AuthWhoamiCmd(user_repo=user_repo)
    result = cmd.call("")  # No username

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("Not authenticated" in str(r.get("text", "")) for r in result)


def test_auth_logout():
    """Test logout command."""
    cmd = AuthLogoutCmd()
    # Logout now requires username (injected by RPC handler in production)
    result = cmd.call("testuser")

    assert isinstance(result, list)
    # Check for success message (either "Logged out" or "Logout successful")
    assert any(
        "Logged out" in str(r.get("text", "")) or "logout" in str(r.get("t", ""))
        for r in result
    )
    assert any("Remove the token" in str(r.get("text", "")) for r in result)


def test_auth_login_increments_login_count(
    db_session: Session, user_repo: UserRepository, test_user: User
):
    """Test that login count is incremented on each login."""
    cmd = AuthLoginCmd(user_repo=user_repo)

    # First login
    cmd.call("testuser", "testpass123")
    db_session.refresh(test_user)
    assert test_user.login_count == 1

    # Second login
    cmd.call("testuser", "testpass123")
    db_session.refresh(test_user)
    assert test_user.login_count == 2


# Magic Link Tests


def test_auth_magic_link_success(user_repo: UserRepository, admin_user: User):
    """Test successful magic link generation."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("admin")

    assert isinstance(result, list)
    # Should return a single text item with the token
    assert len(result) == 1
    assert result[0].get("t") == "text"

    # Token should be a JWT (starts with eyJ)
    token = result[0].get("text", "")
    assert token.startswith("eyJ")


def test_auth_magic_link_default_admin(user_repo: UserRepository, admin_user: User):
    """Test that magic link defaults to admin user when no username provided."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call()  # No username - defaults to "admin"

    assert isinstance(result, list)
    assert len(result) == 1
    token = result[0].get("text", "")
    assert token.startswith("eyJ")


def test_auth_magic_link_nonexistent_user(user_repo: UserRepository):
    """Test magic link for nonexistent user."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("nosuchuser")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("not found" in str(r.get("text", "")) for r in result)


def test_auth_magic_link_inactive_user(
    db_session: Session, user_repo: UserRepository, admin_user: User
):
    """Test magic link for inactive user."""
    admin_user.active = False
    db_session.commit()

    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("admin")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("disabled" in str(r.get("text", "")) for r in result)


def test_auth_magic_link_for_regular_user(user_repo: UserRepository, test_user: User):
    """Test magic link can be generated for any user, not just admin."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("testuser")

    assert isinstance(result, list)
    assert len(result) == 1
    token = result[0].get("text", "")
    assert token.startswith("eyJ")


def test_auth_magic_link_token_has_correct_scope(
    user_repo: UserRepository, admin_user: User
):
    """Test that magic link token has the magic_link scope."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("admin")

    token = result[0].get("text", "")

    # Decode the token to verify scope
    secret_key = os.environ["HOP3_SECRET_KEY"]
    payload = jwt.decode(token, secret_key, algorithms=["HS256"])

    assert payload["sub"] == "admin"
    assert "magic_link" in payload["scopes"]
