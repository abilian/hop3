# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Two long-standing gaps in the auth controller, closed 2026-08-01.

Both were recorded in security-model.md §3.7 as known and unfixed since the
May 2026 round:

* login over plain HTTP set a `Secure` cookie the browser then discarded, so
  the login looped endlessly with no error — a silent failure, which the
  platform's own rule forbids outright;
* logout was a `GET`, and `samesite=lax` sends the auth cookie on cross-site
  GETs, so any page could log a user out. It was also the single
  state-changing GET that made "every mutation is a POST" — the argument for
  shipping without CSRF tokens — untrue.
"""

from __future__ import annotations

from urllib.parse import unquote

import pytest
from litestar.testing import TestClient

from hop3.server.asgi import create_app


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-auth-transport")


@pytest.fixture
def client():
    # TestClient talks http:// from an untrusted peer, which is exactly the
    # broken pairing: not TLS, and not a proxy we would believe about it.
    return TestClient(create_app())


def test_login_over_plain_http_is_refused_with_a_reason(client: TestClient) -> None:
    """It must say why, rather than issue a cookie that cannot come back."""
    response = client.post(
        "/auth/login",
        data={"username": "someone", "password": "whatever"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303}
    location = unquote(response.headers["location"])
    assert "/auth/login?error=" in location
    assert "plain HTTP" in location
    # No credential was issued: the point is to not pretend the login worked.
    assert "hop3_auth" not in response.cookies


def test_login_page_warns_before_a_password_is_typed(client: TestClient) -> None:
    response = client.get("/auth/login")

    assert response.status_code == 200
    assert "This connection is not secure" in response.text


def test_magic_link_over_plain_http_does_not_burn_the_token(
    client: TestClient,
) -> None:
    """
    Redemption is refused *before* `validate_magic_token` consumes the link.

    A single-use token spent on a login that cannot hold its cookie leaves the
    operator with no way in and no explanation.
    """
    response = client.get("/auth/magic/some-token", follow_redirects=False)

    assert response.status_code in {302, 303}
    assert "plain HTTP" in unquote(response.headers["location"])


def test_logout_is_not_reachable_by_get(client: TestClient) -> None:
    """A logout link is CSRF-able under samesite=lax; a form POST is not."""
    response = client.get("/auth/logout", follow_redirects=False)

    assert response.status_code == 405


def test_logout_accepts_post(client: TestClient) -> None:
    response = client.post("/auth/logout", follow_redirects=False)

    assert response.status_code in {302, 303}
    assert response.headers["location"] == "/auth/login"


def test_no_mutating_get_routes_remain(client: TestClient) -> None:
    """
    The invariant that lets hop3-server ship without CSRF tokens.

    `samesite=lax` blocks the auth cookie on cross-site POSTs but sends it on
    cross-site GETs, so the "no CSRF middleware" decision holds only while
    every state-changing route is a POST. Logout was the exception; this
    fails if another one appears.
    """
    app = create_app()
    mutating = {"logout", "delete", "destroy", "create", "restart", "stop", "restore"}

    offenders = [
        f"{method} {path}"
        for path, handler in app.route_handler_method_map.items()
        for method in handler
        if method == "GET" and any(verb in path.lower() for verb in mutating)
    ]
    assert not offenders, f"State-changing GET routes: {offenders}"
