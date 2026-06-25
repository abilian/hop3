# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""CSRF protection on the state-changing POSTs (active when not UNSAFE).

The rest of the suite runs with TESTLAB_UNSAFE=true (auth + CSRF bypassed); here
we opt back in to confirm the middleware is actually wired and enforcing.
"""

from __future__ import annotations

from litestar.testing import TestClient

from hop3_testlab.web.asgi import create_app


def test_csrf_failure_redirects_to_login_and_clears_wedged_cookie(monkeypatch):
    """A CSRF failure must not dump JSON at the user. The handler bounces to a fresh
    login and expires the (possibly wedged) csrftoken cookie, so the retry works."""
    monkeypatch.setenv("TESTLAB_UNSAFE", "")  # enable CSRF (and the auth guard)
    monkeypatch.setenv("TESTLAB_PASSWORD", "secret")

    with TestClient(app=create_app()) as client:
        client.get("/auth/login")  # mints a valid csrftoken cookie
        assert client.cookies.get("csrftoken")

        # A mismatched token -> CSRF middleware raises -> our handler redirects to
        # login (HTML), not a JSON 403, and clears the cookie.
        blocked = client.post(
            "/auth/login",
            data={"username": "admin", "password": "secret", "_csrf_token": "wrong"},
            follow_redirects=False,
        )
        assert blocked.status_code == 303
        assert blocked.headers["location"].startswith("/auth/login")
        assert client.cookies.get("csrftoken") is None  # wedged cookie cleared


def test_csrf_valid_token_passes_when_not_unsafe(monkeypatch):
    monkeypatch.setenv("TESTLAB_UNSAFE", "")  # enable CSRF (and the auth guard)
    monkeypatch.setenv("TESTLAB_PASSWORD", "secret")

    with TestClient(app=create_app()) as client:
        # Fetch a token (the GET sets the csrftoken cookie), then the same POST
        # passes CSRF — auth is handled separately, so assert only "not a 403".
        client.get("/auth/login")
        token = client.cookies.get("csrftoken")
        assert token
        passed = client.post(
            "/auth/login",
            data={"username": "admin", "password": "secret", "_csrf_token": token},
            follow_redirects=False,
        )
        assert passed.status_code != 403


def test_no_csrf_under_unsafe(monkeypatch):
    """Under the test/dev UNSAFE bypass, POSTs work without a token (so the rest
    of the suite — and local dev — isn't forced to round-trip one)."""
    monkeypatch.setenv("TESTLAB_UNSAFE", "true")
    with TestClient(app=create_app()) as client:
        r = client.post("/running/stop")
    assert r.status_code != 403
