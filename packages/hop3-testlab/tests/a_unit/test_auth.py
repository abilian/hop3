# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Session-cookie auth: the guard, login, and logout.

The autouse conftest sets TESTLAB_UNSAFE=true (bypass); these tests opt back into
enforcement with TESTLAB_UNSAFE=false.
"""

from __future__ import annotations

from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient


def test_dashboard_redirects_to_login_when_unauthenticated(monkeypatch):
    monkeypatch.setenv("TESTLAB_UNSAFE", "false")
    with TestClient(app=create_app()) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert "/auth/login" in response.headers.get("location", "")


def test_login_page_is_public(monkeypatch):
    monkeypatch.setenv("TESTLAB_UNSAFE", "false")
    with TestClient(app=create_app()) as client:
        response = client.get("/auth/login")
    assert response.status_code == 200
    assert "Sign in" in response.text


def test_login_grants_access(monkeypatch):
    monkeypatch.setenv("TESTLAB_UNSAFE", "false")
    monkeypatch.setenv("TESTLAB_USERNAME", "admin")
    monkeypatch.setenv("TESTLAB_PASSWORD", "s3cret")
    with TestClient(app=create_app()) as client:
        client.get("/auth/login")  # sets the csrftoken cookie (CSRF is on here)
        token = client.cookies.get("csrftoken")
        login = client.post(
            "/auth/login",
            data={"username": "admin", "password": "s3cret", "_csrf_token": token},
            follow_redirects=False,
        )
        assert login.status_code == 303
        # The session cookie is now set on the client → protected page works.
        page = client.get("/")
    assert page.status_code == 200
    assert "Hop3 Test Lab" in page.text


def test_login_rejects_bad_credentials(monkeypatch):
    monkeypatch.setenv("TESTLAB_UNSAFE", "false")
    monkeypatch.setenv("TESTLAB_PASSWORD", "s3cret")
    with TestClient(app=create_app()) as client:
        client.get("/auth/login")  # sets the csrftoken cookie (CSRF is on here)
        token = client.cookies.get("csrftoken")
        response = client.post(
            "/auth/login",
            data={"username": "admin", "password": "wrong", "_csrf_token": token},
        )
    assert response.status_code == 200
    assert "Invalid credentials" in response.text


def test_health_is_public(monkeypatch):
    monkeypatch.setenv("TESTLAB_UNSAFE", "false")
    with TestClient(app=create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
