# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for auth_guard's dual-credential acceptance.

Regression: the guard used to accept ONLY a web session cookie. A
token-only client (the CLI streaming deploy logs from
``/api/stream/<id>``) therefore failed the guard, got redirected to
``/auth/login`` by ``handle_401``, and — unable to follow the redirect —
reported the deploy as an opaque stream failure. The guard must accept
the same Bearer token ``/rpc`` accepts.
"""

from __future__ import annotations

import pytest
from litestar.exceptions import NotAuthorizedException

from hop3.server import guards
from hop3.server.guards import auth_guard


class _FakeConnection:
    """Minimal ASGIConnection stand-in: just .headers and .session."""

    def __init__(
        self,
        *,
        session: dict | None = None,
        headers: dict | None = None,
    ) -> None:
        self.session = session or {}
        # Header lookup is case-insensitive in Litestar; the guard reads
        # "authorization" lowercase, so a plain dict is enough here.
        self._headers = headers or {}

    @property
    def headers(self):
        return self._headers


@pytest.fixture(autouse=True)
def _force_safe_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the guard exercises the real auth path (not the UNSAFE bypass)."""
    monkeypatch.setattr(guards.config, "HOP3_UNSAFE", False)


# ---- session-cookie path -------------------------------------------------


def test_session_cookie_authenticates() -> None:
    conn = _FakeConnection(session={"user_id": "alice"})
    auth_guard(conn, None)  # must not raise


def test_no_credentials_rejected() -> None:
    conn = _FakeConnection()
    with pytest.raises(NotAuthorizedException):
        auth_guard(conn, None)


# ---- bearer-token path (the fix) ----------------------------------------


def test_valid_bearer_token_authenticates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        guards, "validate_token", lambda t: {"username": "bob", "scopes": ["admin"]}
    )
    conn = _FakeConnection(headers={"authorization": "Bearer good-token"})
    auth_guard(conn, None)  # must not raise


def test_bearer_scheme_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guards, "validate_token", lambda t: {"username": "bob"})
    conn = _FakeConnection(headers={"authorization": "bearer good-token"})
    auth_guard(conn, None)  # must not raise


def test_invalid_bearer_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guards, "validate_token", lambda t: None)
    conn = _FakeConnection(headers={"authorization": "Bearer bad-token"})
    with pytest.raises(NotAuthorizedException):
        auth_guard(conn, None)


def test_non_bearer_authorization_header_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Basic-auth header must not be treated as a token, and validate_token
    # must not even be consulted for it.
    called = {"hit": False}

    def _spy(_t):
        called["hit"] = True
        return {"username": "x"}

    monkeypatch.setattr(guards, "validate_token", _spy)
    conn = _FakeConnection(headers={"authorization": "Basic dXNlcjpwYXNz"})
    with pytest.raises(NotAuthorizedException):
        auth_guard(conn, None)
    assert called["hit"] is False


def test_session_cookie_wins_without_consulting_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A logged-in session short-circuits before token validation."""
    called = {"hit": False}

    def _spy(_t):
        called["hit"] = True

    monkeypatch.setattr(guards, "validate_token", _spy)
    conn = _FakeConnection(
        session={"user_id": "alice"},
        headers={"authorization": "Bearer whatever"},
    )
    auth_guard(conn, None)
    assert called["hit"] is False


def test_bearer_token_does_not_mutate_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard authorises without issuing a session (no surprise cookie
    for a Bearer client)."""
    monkeypatch.setattr(guards, "validate_token", lambda t: {"username": "bob"})
    conn = _FakeConnection(headers={"authorization": "Bearer good-token"})
    auth_guard(conn, None)
    assert conn.session == {}


# ---- unsafe-mode bypass --------------------------------------------------


def test_unsafe_mode_skips_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guards.config, "HOP3_UNSAFE", True)
    conn = _FakeConnection()  # no creds at all
    auth_guard(conn, None)  # must not raise
