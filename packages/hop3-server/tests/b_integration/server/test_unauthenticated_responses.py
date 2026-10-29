# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
An unauthenticated caller is sent to sign in, in a form it can act on.

`handle_401` redirected everything to the HTML login page: the CLI streaming a
deploy from `/api/stream/*` got a page it cannot parse, and an HTMX request
followed the redirect and swapped the login page into its fragment.
"""

from __future__ import annotations

import pytest
from litestar.testing import TestClient

from hop3.server.asgi import create_app


@pytest.fixture
def client(monkeypatch, file_db):
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-401-responses")
    return TestClient(create_app())


def test_an_api_client_gets_json(client):
    response = client.get(
        "/api/stream/00000000-0000-0000-0000-000000000000", follow_redirects=False
    )

    assert response.status_code == 401
    assert response.json()["status_code"] == 401


def test_an_htmx_request_is_told_where_to_go(client):
    response = client.get(
        "/dashboard/", headers={"HX-Request": "true"}, follow_redirects=False
    )

    assert response.status_code == 401
    assert response.headers["HX-Redirect"] == "/auth/login"


def test_a_browser_is_redirected_to_the_login_page(client):
    response = client.get("/dashboard/", follow_redirects=False)

    assert response.status_code in {302, 303, 307}
    assert response.headers["location"] == "/auth/login"
