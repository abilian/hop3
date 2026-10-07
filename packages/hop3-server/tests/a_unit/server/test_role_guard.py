# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the dashboard's role guard (ADR 061 §4).

The guard accepts the single signed JWT credential over either transport: the
``hop3_auth`` cookie (dashboard) or an ``Authorization: Bearer`` header (CLI /
API), via ``current_identity``, with no server-side session. Then it reads the
account the token names and admits it only when active and in a role at least
the route's.

Regression: the guard once accepted ONLY a web session cookie, so a token-only
client (the CLI streaming deploy logs from ``/api/stream/<id>``) failed the
guard, got redirected to ``/auth/login`` by ``handle_401``, and — unable to
follow the redirect — reported the deploy as an opaque stream failure. It must
accept the same token ``/rpc`` accepts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import anyio
import pytest
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException

from hop3.core.roles import Role
from hop3.server import guards
from hop3.server.guards import RoleGuard
from hop3.server.security.authorization import Account
from hop3.server.security.web_auth import AUTH_COOKIE, issue_web_token

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers import BaseRouteHandler


def _run_guard(conn: object, required: Role = Role.VIEWER) -> None:
    """Run a role guard (async) with the test double cast to the declared types."""
    anyio.run(
        RoleGuard(required),
        cast("ASGIConnection", conn),
        cast("BaseRouteHandler", None),
    )


class _FakeConnection:
    """
    Minimal ASGIConnection stand-in: just .headers and .cookies.

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


#: The accounts the stubbed lookup knows; any other name has no account.
ACCOUNTS = {
    "alice": Account(username="alice", role=Role.VIEWER, active=True),
    "bob": Account(username="bob", role=Role.DEPLOYER, active=True),
    "mia": Account(username="mia", role=Role.MEMBER, active=True),
    "dan": Account(username="dan", role=Role.ADMIN, active=False),
}


@pytest.fixture(autouse=True)
def _force_safe_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the real auth path (not the UNSAFE bypass) with a stable key."""
    monkeypatch.setattr(guards.config, "HOP3_UNSAFE", False)
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-for-auth-guard-padding")
    monkeypatch.setattr(guards, "lookup_account", ACCOUNTS.get)


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


# ---- roles ---------------------------------------------------------------


def test_a_role_below_the_route_is_refused() -> None:
    conn = _FakeConnection(cookies={AUTH_COOKIE: issue_web_token("mia")})
    with pytest.raises(PermissionDeniedException, match="needs the viewer role"):
        _run_guard(conn)


def test_a_higher_role_is_admitted() -> None:
    conn = _FakeConnection(cookies={AUTH_COOKIE: issue_web_token("bob")})
    _run_guard(conn, Role.VIEWER)  # must not raise


def test_a_token_naming_no_account_is_refused() -> None:
    conn = _FakeConnection(cookies={AUTH_COOKIE: issue_web_token("ghost")})
    with pytest.raises(NotAuthorizedException):
        _run_guard(conn)


def test_a_disabled_account_is_refused() -> None:
    conn = _FakeConnection(cookies={AUTH_COOKIE: issue_web_token("dan")})
    with pytest.raises(NotAuthorizedException):
        _run_guard(conn, Role.MEMBER)
