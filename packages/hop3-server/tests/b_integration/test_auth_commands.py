# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for authentication commands."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from hop3.commands.auth import (
    AuthLoginCmd,
    AuthLogoutCmd,
    AuthRegisterCmd,
    AuthWhoamiCmd,
)
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


def test_auth_register_success(db_session: Session):
    """Test successful user registration."""
    cmd = AuthRegisterCmd(db_session=db_session)
    result = cmd.call("newuser", "new@example.com", "password123")

    assert isinstance(result, list)
    assert any("registered successfully" in str(r.get("text", "")) for r in result)

    # Verify user was created in database
    user = db_session.query(User).filter_by(username="newuser").first()
    assert user is not None
    assert user.email == "new@example.com"
    assert user.check_password("password123")
    assert user.active is True


def test_auth_register_missing_params(db_session: Session):
    """Test registration with missing parameters."""
    cmd = AuthRegisterCmd(db_session=db_session)
    result = cmd.call("newuser", "", "")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_register_duplicate_username(db_session: Session, test_user: User):
    """Test registration with duplicate username."""
    cmd = AuthRegisterCmd(db_session=db_session)
    result = cmd.call("testuser", "different@example.com", "password")

    assert isinstance(result, list)
    assert any("already exists" in str(r.get("text", "")) for r in result)


def test_auth_register_duplicate_email(db_session: Session, test_user: User):
    """Test registration with duplicate email."""
    cmd = AuthRegisterCmd(db_session=db_session)
    result = cmd.call("differentuser", "test@example.com", "password")

    assert isinstance(result, list)
    assert any("already registered" in str(r.get("text", "")) for r in result)


def test_auth_login_success(db_session: Session, test_user: User):
    """Test successful login."""
    cmd = AuthLoginCmd(db_session=db_session)
    result = cmd.call("testuser", "testpass123")

    assert isinstance(result, list)
    assert any("Login successful" in str(r.get("text", "")) for r in result)

    # Check that a token was returned
    assert any("Your API token:" in str(r.get("text", "")) for r in result)

    # Verify login tracking was updated
    db_session.refresh(test_user)
    assert test_user.login_count == 1
    assert test_user.current_login_at is not None


def test_auth_login_wrong_password(db_session: Session, test_user: User):
    """Test login with wrong password."""
    cmd = AuthLoginCmd(db_session=db_session)
    result = cmd.call("testuser", "wrongpassword")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("Invalid username or password" in str(r.get("text", "")) for r in result)


def test_auth_login_nonexistent_user(db_session: Session):
    """Test login with nonexistent user."""
    cmd = AuthLoginCmd(db_session=db_session)
    result = cmd.call("nosuchuser", "password")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_login_inactive_user(db_session: Session, test_user: User):
    """Test login with inactive user."""
    test_user.active = False
    db_session.commit()

    cmd = AuthLoginCmd(db_session=db_session)
    result = cmd.call("testuser", "testpass123")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("disabled" in str(r.get("text", "")) for r in result)


def test_auth_login_missing_params(db_session: Session):
    """Test login with missing parameters."""
    cmd = AuthLoginCmd(db_session=db_session)
    result = cmd.call("", "")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_login_admin_user_gets_admin_scope(db_session: Session, admin_user: User):
    """Test that admin users get admin scope in their token."""
    cmd = AuthLoginCmd(db_session=db_session)
    result = cmd.call("admin", "adminpass")

    assert isinstance(result, list)
    assert any("Login successful" in str(r.get("text", "")) for r in result)

    # The token should be in the result - we could decode it to verify admin scope
    # but for now just check that login succeeded


def test_auth_whoami_success(db_session: Session, test_user: User):
    """Test whoami command."""
    cmd = AuthWhoamiCmd(db_session=db_session)
    result = cmd.call("testuser")  # Username would come from auth middleware

    assert isinstance(result, list)
    assert any("testuser" in str(r.get("text", "")) for r in result)
    assert any("test@example.com" in str(r.get("text", "")) for r in result)


def test_auth_whoami_no_username(db_session: Session):
    """Test whoami without username (not authenticated)."""
    cmd = AuthWhoamiCmd(db_session=db_session)
    result = cmd.call("")  # No username

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("Not authenticated" in str(r.get("text", "")) for r in result)


def test_auth_logout(db_session: Session):
    """Test logout command."""
    cmd = AuthLogoutCmd()
    result = cmd.call()

    assert isinstance(result, list)
    assert any("Logout successful" in str(r.get("text", "")) for r in result)
    assert any("Remove the token" in str(r.get("text", "")) for r in result)


def test_auth_login_increments_login_count(db_session: Session, test_user: User):
    """Test that login count is incremented on each login."""
    cmd = AuthLoginCmd(db_session=db_session)

    # First login
    cmd.call("testuser", "testpass123")
    db_session.refresh(test_user)
    assert test_user.login_count == 1

    # Second login
    cmd.call("testuser", "testpass123")
    db_session.refresh(test_user)
    assert test_user.login_count == 2
