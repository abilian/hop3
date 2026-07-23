# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from hop3.orm import User
from hop3.orm.security import AuditBase


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


def test_user_password_hashing(db_session: Session):
    """
    Test password hashing and verification.

    NB: slow test due to hashing computation.
    """
    user = User(username="testuser", email="test@example.com", password_hash="")
    user.set_password("mysecretpassword")

    db_session.add(user)
    db_session.commit()

    # Correct password should verify
    assert user.check_password("mysecretpassword")

    # Incorrect password should not verify
    assert not user.check_password("wrongpassword")
    assert not user.check_password("")
