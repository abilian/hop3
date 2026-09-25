# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the User model and its role."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from hop3.core.roles import Role
from hop3.orm.security import AuditBase, User


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


def test_a_new_user_is_a_member(db_session: Session):
    """ADR 061 §2: no "no role" state; ``member`` is the floor."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.role is Role.MEMBER
    assert not user.is_admin


def test_user_is_admin_follows_the_role(db_session: Session):
    user = User(username="testuser", email="test@example.com", password_hash="")
    user.role = Role.ADMIN
    db_session.add(user)
    db_session.commit()

    assert user.is_admin


def test_the_role_is_stored_by_value(db_session: Session):
    """The column reads "deployer", not the enum member's name "DEPLOYER"."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    user.role = Role.DEPLOYER
    db_session.add(user)
    db_session.commit()

    stored = db_session.execute(text("SELECT role FROM sec_user")).scalar_one()
    assert stored == "deployer"


def test_user_unique_username(db_session: Session):
    """Test that username must be unique."""
    user1 = User(username="testuser", email="test1@example.com", password_hash="hash1")
    user2 = User(username="testuser", email="test2@example.com", password_hash="hash2")

    db_session.add(user1)
    db_session.commit()

    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_unique_email(db_session: Session):
    """Test that email must be unique."""
    user1 = User(username="user1", email="test@example.com", password_hash="hash1")
    user2 = User(username="user2", email="test@example.com", password_hash="hash2")

    db_session.add(user1)
    db_session.commit()

    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_user_repr(db_session: Session):
    """Test user string representation."""
    user = User(username="testuser", email="test@example.com", password_hash="")
    assert "testuser" in repr(user)
    assert "test@example.com" in repr(user)
