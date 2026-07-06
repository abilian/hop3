# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Stateless web auth: a signed JWT cookie, no server-side session.

The dashboard identity rides the same signed JWT the CLI uses, in an httponly
cookie, so it survives restarts/redeploys (the secret persists) and needs no
store. ``current_identity`` accepts the token from the cookie or the
Authorization header.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.server.security.tokens import create_token
from hop3.server.security.web_auth import (
    AUTH_COOKIE,
    WEB_SESSION_EXPIRY_HOURS,
    auth_cookie,
    clear_auth_cookie,
    current_identity,
    extract_token,
    issue_web_token,
)


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    # get_secret_key() reads /etc/hop3/secret-key, then HOP3_SECRET_KEY.
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-for-web-auth--padding")


def _conn(*, bearer: str | None = None, cookie: str | None = None):
    headers = {"authorization": f"Bearer {bearer}"} if bearer is not None else {}
    cookies = {AUTH_COOKIE: cookie} if cookie is not None else {}
    return SimpleNamespace(headers=headers, cookies=cookies)


def test_token_roundtrip_carries_username():
    identity = current_identity(_conn(cookie=issue_web_token("admin")))
    assert identity is not None
    assert identity["username"] == "admin"


def test_identity_from_authorization_header():
    identity = current_identity(_conn(bearer=issue_web_token("alice")))
    assert identity is not None
    assert identity["username"] == "alice"


def test_header_wins_over_cookie():
    """A client that sends an Authorization header gets header semantics."""
    assert extract_token(_conn(bearer="HEADER", cookie="COOKIE")) == "HEADER"


def test_extract_prefers_cookie_when_no_header():
    assert extract_token(_conn(cookie="COOKIE")) == "COOKIE"


def test_empty_bearer_falls_through_to_cookie():
    """`Authorization: Bearer ` (empty) must not mask a valid cookie."""
    assert extract_token(_conn(bearer="", cookie="COOKIE")) == "COOKIE"


def test_empty_subject_token_is_rejected():
    """A token with an empty `sub` must not authenticate (no blank username)."""
    assert current_identity(_conn(cookie=create_token(""))) is None


def test_no_credential_is_anonymous():
    assert current_identity(_conn()) is None


def test_garbage_token_is_rejected():
    assert current_identity(_conn(cookie="not-a-jwt")) is None


def test_auth_cookie_is_httponly_and_long_lived():
    cookie = auth_cookie("admin")
    assert cookie.key == AUTH_COOKIE
    assert cookie.httponly is True
    assert cookie.samesite == "lax"
    assert cookie.max_age == WEB_SESSION_EXPIRY_HOURS * 3600
    # The cookie value is a valid token for the user.
    assert current_identity(_conn(cookie=cookie.value))["username"] == "admin"


def test_clear_cookie_expires_immediately():
    cookie = clear_auth_cookie()
    assert cookie.key == AUTH_COOKIE
    assert cookie.value == ""
    assert cookie.max_age == 0
