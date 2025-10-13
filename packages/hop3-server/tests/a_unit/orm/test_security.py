# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for User and Role models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from hop3.orm.security import AuditBase, Role, User


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


def test_user_creation(db_session: Session):
    """Test creating a user."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    user.set_password("testpass123")

    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.password_hash != ""
    assert user.password_hash != "testpass123"  # Should be hashed


def test_user_password_hashing(db_session: Session):
    """Test password hashing and verification."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    user.set_password("mysecretpassword")

    db_session.add(user)
    db_session.commit()

    # Correct password should verify
    assert user.check_password("mysecretpassword")

    # Incorrect password should not verify
    assert not user.check_password("wrongpassword")
    assert not user.check_password("")


def test_user_active_default(db_session: Session):
    """Test that user is active by default."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    db_session.add(user)
    db_session.commit()

    assert user.active is True


def test_user_login_tracking(db_session: Session):
    """Test login tracking fields."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    user.set_password("password")

    db_session.add(user)
    db_session.commit()

    # Initially no logins
    assert user.login_count == 0
    assert user.last_login_at is None
    assert user.current_login_at is None

    # Simulate a login
    user.current_login_at = datetime.now(timezone.utc)
    user.current_login_ip = "192.168.1.1"
    user.login_count += 1
    db_session.commit()

    assert user.login_count == 1
    assert user.current_login_at is not None
    assert user.current_login_ip == "192.168.1.1"


def test_role_creation(db_session: Session):
    """Test creating a role."""
    role = Role(name="admin", description="Administrator role")

    db_session.add(role)
    db_session.commit()

    assert role.id is not None
    assert role.name == "admin"
    assert role.description == "Administrator role"


def test_user_roles_relationship(db_session: Session):
    """Test many-to-many relationship between users and roles."""
    # Create user and roles
    user = User(username="testuser", email="test@example.com", password_hash="")
    admin_role = Role(name="admin", description="Admin")
    user_role = Role(name="user", description="Regular user")

    db_session.add(user)
    db_session.add(admin_role)
    db_session.add(user_role)
    db_session.commit()

    # Assign roles to user
    user.roles.append(admin_role)
    user.roles.append(user_role)
    db_session.commit()

    # Check roles are assigned
    assert len(user.roles) == 2
    role_names = {role.name for role in user.roles}
    assert "admin" in role_names
    assert "user" in role_names


def test_user_has_role(db_session: Session):
    """Test has_role method."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    admin_role = Role(name="admin", description="Admin")
    user_role = Role(name="user", description="User")

    user.roles.append(admin_role)
    user.roles.append(user_role)

    db_session.add(user)
    db_session.commit()

    assert user.has_role("admin")
    assert user.has_role("user")
    assert not user.has_role("moderator")


def test_user_is_admin(db_session: Session):
    """Test is_admin property."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    admin_role = Role(name="admin", description="Admin")

    db_session.add(user)
    db_session.add(admin_role)
    db_session.commit()

    # User without admin role
    assert not user.is_admin

    # User with admin role
    user.roles.append(admin_role)
    db_session.commit()

    assert user.is_admin


def test_user_unique_username(db_session: Session):
    """Test that username must be unique."""
    user1 = User(username="testuser", email="test1@example.com", password_hash="hash1")
    user2 = User(username="testuser", email="test2@example.com", password_hash="hash2")

    db_session.add(user1)
    db_session.commit()

    db_session.add(user2)

    with pytest.raises(Exception):  # Should raise IntegrityError
        db_session.commit()


def test_user_unique_email(db_session: Session):
    """Test that email must be unique."""
    user1 = User(username="user1", email="test@example.com", password_hash="hash1")
    user2 = User(username="user2", email="test@example.com", password_hash="hash2")

    db_session.add(user1)
    db_session.commit()

    db_session.add(user2)

    with pytest.raises(Exception):  # Should raise IntegrityError
        db_session.commit()


def test_role_unique_name(db_session: Session):
    """Test that role name must be unique."""
    role1 = Role(name="admin", description="Admin 1")
    role2 = Role(name="admin", description="Admin 2")

    db_session.add(role1)
    db_session.commit()

    db_session.add(role2)

    with pytest.raises(Exception):  # Should raise IntegrityError
        db_session.commit()


def test_user_repr(db_session: Session):
    """Test user string representation."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    assert "testuser" in repr(user)
    assert "test@example.com" in repr(user)


def test_role_repr(db_session: Session):
    """Test role string representation."""
    role = Role(name="admin", description="Administrator")
    assert "admin" in repr(role)
