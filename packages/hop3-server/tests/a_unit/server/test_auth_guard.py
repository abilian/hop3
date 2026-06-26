# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for auth_guard's stateless credential acceptance.

The guard accepts the single signed JWT credential over either transport: the
``hop3_auth`` cookie (dashboard) or an ``Authorization: Bearer`` header (CLI /
API) — via ``current_identity``, with no server-side session.

Regression: the guard once accepted ONLY a web session cookie, so a token-only
client (the CLI streaming deploy logs from ``/api/stream/<id>``) failed the
guard, got redirected to ``/auth/login`` by ``handle_401``, and — unable to
follow the redirect — reported the deploy as an opaque stream failure. It must
accept the same token ``/rpc`` accepts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from litestar.exceptions import NotAuthorizedException

from hop3.server import guards
from hop3.server.guards import auth_guard
from hop3.server.security.web_auth import AUTH_COOKIE, issue_web_token

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers import BaseRouteHandler


def _run_guard(conn: object) -> None:
    """Call auth_guard with the test double cast to the declared types."""
    auth_guard(cast("ASGIConnection", conn), cast("BaseRouteHandler", None))


class _FakeConnection:
    """Minimal ASGIConnection stand-in: just .headers and .cookies.

    Header lookup is case-insensitive in Litestar; the auth code reads
    "authorization" lowercase, so a plain dict is enough here.
    """

    def __init__(
        self,
        *,
        headers: dict | None = None,
        cookies: dict | None = None,
    ) -> None:
        self._headers = headers or {}
        self.cookies = cookies or {}

    @property
    def headers(self):
        return self._headers


@pytest.fixture(autouse=True)
def _force_safe_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the real auth path (not the UNSAFE bypass) with a stable key."""
    monkeypatch.setattr(guards.config, "HOP3_UNSAFE", False)
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-for-auth-guard-padding")


# ---- cookie path (dashboard) --------------------------------------------


def test_cookie_authenticates() -> None:
    conn = _FakeConnection(cookies={AUTH_COOKIE: issue_web_token("alice")})
    _run_guard(conn)  # must not raise


# ---- bearer-token path (CLI / API — the streaming-client regression) -----


def test_valid_bearer_token_authenticates() -> None:
    conn = _FakeConnection(
        headers={"authorization": f"Bearer {issue_web_token('bob')}"}
    )
    _run_guard(conn)  # must not raise


def test_bearer_scheme_is_case_insensitive() -> None:
    conn = _FakeConnection(
        headers={"authorization": f"bearer {issue_web_token('bob')}"}
    )
    _run_guard(conn)  # must not raise


def test_invalid_bearer_token_rejected() -> None:
    conn = _FakeConnection(headers={"authorization": "Bearer not-a-jwt"})
    with pytest.raises(NotAuthorizedException):
        _run_guard(conn)


def test_non_bearer_authorization_header_rejected() -> None:
    conn = _FakeConnection(headers={"authorization": "Basic dXNlcjpwYXNz"})
    with pytest.raises(NotAuthorizedException):
        _run_guard(conn)


# ---- no credential -------------------------------------------------------


def test_no_credentials_rejected() -> None:
    with pytest.raises(NotAuthorizedException):
        _run_guard(_FakeConnection())


def test_garbage_cookie_rejected() -> None:
    conn = _FakeConnection(cookies={AUTH_COOKIE: "tampered"})
    with pytest.raises(NotAuthorizedException):
        _run_guard(conn)


# ---- unsafe-mode bypass --------------------------------------------------


def test_unsafe_mode_skips_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guards.config, "HOP3_UNSAFE", True)
    _run_guard(_FakeConnection())  # no creds at all — must not raise
