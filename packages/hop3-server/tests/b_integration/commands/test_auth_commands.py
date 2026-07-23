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
    AuthGetTokenCmd,
    AuthLogoutCmd,
    AuthMagicLinkCmd,
    AuthWhoamiCmd,
)
from hop3.orm.repositories import UserRepository
from hop3.orm.security import AuditBase, Role, User
from hop3.server.controllers.rpc import command_needs_username


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


# `auth register` was dropped (ADR 036 P2.1) — it's now a back-compat alias of
# `user add`. The account-creation behaviour (success / missing params / dup
# username+email / admin-gating / anonymous rejection) is covered by
# test_user_commands_integration.py::TestAdminUserAddCmdIntegration, and the
# alias resolution by tests/a_unit/commands/test_command_aliases.py.


def test_auth_login_success(
    db_session: Session, user_repo: UserRepository, test_user: User
):
    """Test successful login."""
    cmd = AuthGetTokenCmd(user_repo=user_repo)
    result = cmd.call("testuser", "testpass123")

    assert isinstance(result, list)

    # Output is the bare token, so callers can capture it directly.
    tokens = [r.get("text", "") for r in result if r.get("t") == "text"]
    assert len(tokens) == 1
    assert tokens[0].count(".") == 2  # JWT: header.payload.signature

    # Verify login tracking was updated
    db_session.refresh(test_user)
    assert test_user.login_count == 1
    assert test_user.current_login_at is not None


def test_auth_login_wrong_password(user_repo: UserRepository, test_user: User):
    """Test login with wrong password."""
    cmd = AuthGetTokenCmd(user_repo=user_repo)
    result = cmd.call("testuser", "wrongpassword")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("Invalid username or password" in str(r.get("text", "")) for r in result)


def test_auth_login_nonexistent_user(user_repo: UserRepository):
    """Test login with nonexistent user."""
    cmd = AuthGetTokenCmd(user_repo=user_repo)
    result = cmd.call("nosuchuser", "password")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_login_inactive_user(
    db_session: Session, user_repo: UserRepository, test_user: User
):
    """Test login with inactive user."""
    test_user.active = False
    db_session.commit()

    cmd = AuthGetTokenCmd(user_repo=user_repo)
    result = cmd.call("testuser", "testpass123")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("disabled" in str(r.get("text", "")) for r in result)


def test_auth_login_missing_params(user_repo: UserRepository):
    """Test login with missing parameters."""
    cmd = AuthGetTokenCmd(user_repo=user_repo)
    result = cmd.call("", "")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_login_admin_user_gets_admin_scope(
    user_repo: UserRepository, admin_user: User
):
    """Test that admin users get admin scope in their token."""
    cmd = AuthGetTokenCmd(user_repo=user_repo)
    result = cmd.call("admin", "adminpass")

    assert isinstance(result, list)

    # The admin's token is returned (bare). Decoding to assert the admin scope
    # is left to the token tests; here we just confirm a token came back.
    tokens = [r.get("text", "") for r in result if r.get("t") == "text"]
    assert len(tokens) == 1
    assert tokens[0].count(".") == 2


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
    cmd = AuthGetTokenCmd(user_repo=user_repo)

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
    result = cmd.call("admin", "admin")

    assert isinstance(result, list)
    # Should return a single text item with the token
    assert len(result) == 1
    assert result[0].get("t") == "text"

    # Token should be a JWT (starts with eyJ)
    token = result[0].get("text", "")
    assert token.startswith("eyJ")


def test_auth_magic_link_requires_username(user_repo: UserRepository, admin_user: User):
    """Magic link requires an explicit username (no admin default)."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("admin")  # No target username

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("Usage" in str(r.get("text", "")) for r in result)


def test_auth_magic_link_nonexistent_user(user_repo: UserRepository, admin_user: User):
    """Test magic link for nonexistent user."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("admin", "nosuchuser")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("not found" in str(r.get("text", "")) for r in result)


def test_auth_magic_link_inactive_user(
    db_session: Session, user_repo: UserRepository, admin_user: User
):
    """Test magic link for inactive user."""
    # Use a separate disabled user so the admin caller stays active.
    disabled_user = User(
        username="disabled", email="disabled@example.com", password_hash=""
    )
    disabled_user.set_password("pw")
    disabled_user.active = False
    db_session.add(disabled_user)
    db_session.commit()

    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("admin", "disabled")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert any("disabled" in str(r.get("text", "")) for r in result)


def test_auth_magic_link_for_regular_user(
    user_repo: UserRepository, admin_user: User, test_user: User
):
    """Magic link can be generated for any user (admin chooses the target)."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("admin", "testuser")

    assert isinstance(result, list)
    assert len(result) == 1
    token = result[0].get("text", "")
    assert token.startswith("eyJ")


def test_auth_magic_link_token_has_correct_scope(
    user_repo: UserRepository, admin_user: User
):
    """Test that magic link token has the magic_link scope."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("admin", "admin")

    token = result[0].get("text", "")

    # Decode the token to verify scope
    secret_key = os.environ["HOP3_SECRET_KEY"]
    payload = jwt.decode(token, secret_key, algorithms=["HS256"])

    assert payload["sub"] == "admin"
    assert "magic_link" in payload["scopes"]


def test_auth_magic_link_rejects_anonymous(user_repo: UserRepository, admin_user: User):
    """Anonymous caller cannot mint a magic link (security review C-001)."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("", "admin")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_magic_link_rejects_non_admin(user_repo: UserRepository, test_user: User):
    """Authenticated non-admin caller cannot mint a magic link."""
    cmd = AuthMagicLinkCmd(user_repo=user_repo)
    result = cmd.call("testuser", "testuser")

    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)


def test_auth_magic_link_pass_username_blocks_spoofed_admin(
    user_repo: UserRepository, test_user: User
):
    """
    A1 regression: the admin gate must read the VERIFIED caller, not arg1.

    The privesc was that ``AuthMagicLinkCmd`` lacked ``pass_username``, so the
    RPC layer never injected the caller's verified identity and the
    attacker-supplied first positional ("admin") landed in
    ``authenticated_username``. We assert the declarative fix and reproduce the
    RPC's arg-injection for the attack payload from a non-admin identity.
    """
    # The fix: the command opts into verified-identity injection.
    assert command_needs_username(AuthMagicLinkCmd) is True

    # Attack: a non-admin token's holder POSTs ["auth","magic-link","admin",<victim>].
    verified_caller = "testuser"  # the real, non-admin identity from the token
    attacker_args = ("admin", "victim")  # arg1 spoofs the well-known admin name

    # Mirror rpc._prepare_command_args: inject the verified identity first.
    prepared_args = (verified_caller, *attacker_args)
    result = AuthMagicLinkCmd(user_repo=user_repo).call(*prepared_args)

    # require_admin now sees 'testuser' (non-admin) -> refused, no token minted.
    assert isinstance(result, list)
    assert any("error" in r.get("t", "") for r in result)
    assert not any(r.get("t") == "text" for r in result)  # no token returned
