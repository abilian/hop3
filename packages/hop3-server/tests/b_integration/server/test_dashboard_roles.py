# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The dashboard admits each account to the pages its role allows (ADR 061 §4).

Through the real app, with real accounts: the role guard reads the account on
every request, and `test_route_roles.py` pins which role each route needs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

from hop3 import config
from hop3.core.roles import Role
from hop3.orm import User
from hop3.server.asgi import create_app
from hop3.server.security import web_auth
from hop3.server.security.web_auth import AUTH_COOKIE

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _real_auth(monkeypatch):
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-dashboard-roles")
    monkeypatch.setattr(config, "HOP3_UNSAFE", False)
    # The auth cookie is `Secure`; the test client speaks plain HTTP.
    monkeypatch.setattr(web_auth, "HOP3_DEBUG", True)


@pytest.fixture
def client(file_db: Session) -> TestClient:
    return TestClient(create_app())


def signed_in(client: TestClient, token: str) -> TestClient:
    client.cookies.set(AUTH_COOKIE, token)
    return client


def test_a_viewer_opens_the_dashboard(client, account: Callable[..., str]):
    viewer = signed_in(client, account("vera", Role.VIEWER))

    assert viewer.get("/dashboard", follow_redirects=False).status_code == 200


def test_a_viewer_is_shown_why_a_secret_page_is_refused(client, account):
    viewer = signed_in(client, account("vera", Role.VIEWER))

    response = viewer.get("/dashboard/apps/anything/env", follow_redirects=False)

    assert response.status_code == 403
    assert "needs the deployer role" in response.text
    assert "hop3 user set-role vera deployer" in response.text


def test_a_member_lands_on_its_profile(client, account):
    account("mia", Role.MEMBER)

    response = client.post(
        "/auth/login",
        data={"username": "mia", "password": "password123"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303}
    assert response.headers["location"] == "/auth/profile"


def test_a_member_is_refused_the_dashboard(client, account):
    member = signed_in(client, account("mia", Role.MEMBER))

    assert member.get("/dashboard", follow_redirects=False).status_code == 403
    assert member.get("/auth/profile", follow_redirects=False).status_code == 200


def test_a_cookie_for_a_deleted_account_gets_the_login_form(client, account, file_db):
    """No loop: the login page must not bounce it back to a refusing guard."""
    ghost = signed_in(client, account("ghost", Role.ADMIN))
    file_db.query(User).filter_by(username="ghost").delete()
    file_db.commit()

    response = ghost.get("/auth/login", follow_redirects=False)

    assert response.status_code == 200


def test_the_deploy_stream_refuses_a_viewer_in_json(client, account):
    token = account("vera", Role.VIEWER)

    response = client.get(
        "/api/stream/some-id", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert "needs the deployer role" in response.json()["detail"]
