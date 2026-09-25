# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The access gate's handshake and check, through the real app (ADR 062).

The proxy's part is played by hand: a request to ``/auth/check`` carries the
headers the proxy sets (``X-Hop3-App``, ``X-Forwarded-Host``, ``-Uri``), and the
callback carries ``X-Hop3-App`` the way the app's vhost routes it. The e2e
suite runs the same flow through nginx, Caddy and Traefik.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import pytest
from litestar.testing import TestClient

from hop3 import config as config_module
from hop3.core.roles import Role
from hop3.orm import App
from hop3.server.asgi import create_app
from hop3.server.security import web_auth
from hop3.server.security.access_gate import GATE_COOKIE, Grant, gate_token
from hop3.server.security.tokens import validate_token
from hop3.server.security.web_auth import AUTH_COOKIE

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

ADMIN = "admin.example.org"
HOST = "notes.example.org"


@pytest.fixture(autouse=True)
def _real_auth(monkeypatch):
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-the-access-gate")
    monkeypatch.setattr(config_module, "HOP3_UNSAFE", False)
    monkeypatch.setattr(web_auth, "HOP3_DEBUG", True)  # the test client is HTTP
    monkeypatch.setattr(
        type(config_module.config), "ADMIN_DOMAIN", property(lambda _self: ADMIN)
    )


@pytest.fixture
def client(file_db: Session) -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def gated(file_db: Session) -> Callable[..., App]:
    def make(name="notes", host=HOST, role=Role.MEMBER, public=()) -> App:
        app = App(
            name=name,
            hostname=host,
            access_role=role,
            access_public_paths=list(public),
        )
        file_db.add(app)
        file_db.commit()
        return app

    return make


def check(client, *, app="notes", host=HOST, uri="/page", cookie="", redirect=False):
    headers = {"X-Hop3-App": app, "X-Forwarded-Host": host, "X-Forwarded-Uri": uri}
    if cookie:
        headers["Cookie"] = cookie
    url = "/auth/check" + ("?redirect=1" if redirect else "")
    client.cookies.clear()
    return client.get(url, headers=headers, follow_redirects=False)


def sign_in(client, username, next_url):
    """Sign in on the admin domain; the redirect it answers with."""
    return client.post(
        "/auth/login",
        data={"username": username, "password": "password123", "next": next_url},
        follow_redirects=False,
    )


def gate_cookie_for(client, username, app="notes", host=HOST, next_path="/page"):
    """Run the handshake; the gate cookie the app's host ends up with."""
    handoff = sign_in(client, username, f"https://{host}{next_path}")
    target = urlsplit(handoff.headers["location"])
    assert (target.netloc, target.path) == (host, "/_hop3/auth/callback")
    callback = client.get(
        f"{target.path}?{target.query}",
        headers={"X-Hop3-App": app},
        follow_redirects=False,
    )
    assert callback.status_code in {302, 303}
    assert callback.headers["location"] == next_path
    set_cookie = callback.headers["set-cookie"]
    assert set_cookie.startswith(f"{GATE_COOKIE}=")
    for attribute in ("Secure", "HttpOnly", "SameSite=lax", "Path=/"):
        assert attribute.lower() in set_cookie.lower()
    assert "domain=" not in set_cookie.lower()
    return set_cookie.split(";", 1)[0].split("=", 1)[1]


def test_an_anonymous_request_is_sent_to_sign_in(client, gated):
    gated()

    response = check(client)

    assert response.status_code == 401
    login = urlsplit(response.headers["x-hop3-login"])
    assert (login.netloc, login.path) == (ADMIN, "/auth/login")
    assert parse_qs(login.query)["next"] == [f"https://{HOST}/page"]


def test_caddy_and_traefik_get_the_redirect_itself(client, gated):
    gated()

    response = check(client, redirect=True)

    assert response.status_code == 302
    assert response.headers["location"].startswith(f"https://{ADMIN}/auth/login?")


def test_a_member_signs_in_and_is_admitted_as_itself(client, gated, account):
    gated()
    account("mia", Role.MEMBER)
    cookie = gate_cookie_for(client, "mia")

    response = check(client, cookie=f"theme=dark; {GATE_COOKIE}={cookie}; lang=fr")

    assert response.status_code == 200
    assert response.headers["x-hop3-user"] == "mia"
    assert response.headers["x-hop3-role"] == "member"
    # What the app receives in place of the request's cookies.
    assert response.headers["cookie"] == "theme=dark; lang=fr"


def test_the_minimum_role_is_enforced(client, gated, account):
    gated(role=Role.VIEWER)
    account("mia", Role.MEMBER)
    account("vera", Role.VIEWER)

    refused = check(client, cookie=f"{GATE_COOKIE}={gate_cookie_for(client, 'mia')}")
    admitted = check(client, cookie=f"{GATE_COOKIE}={gate_cookie_for(client, 'vera')}")

    assert refused.status_code == 403
    assert "hop3 user set-role mia viewer" in refused.text
    assert admitted.status_code == 200


def test_a_public_path_needs_no_sign_in(client, gated):
    gated(public=["/hook"])

    response = check(client, uri="/hook?x=1")

    assert response.status_code == 200
    assert "x-hop3-user" not in response.headers


def test_a_cookie_minted_for_one_app_is_refused_by_another(client, gated, account):
    gated()
    gated(name="wiki", host="wiki.example.org")
    account("mia", Role.MEMBER)
    cookie = gate_cookie_for(client, "mia")

    response = check(
        client, app="wiki", host="wiki.example.org", cookie=f"{GATE_COOKIE}={cookie}"
    )

    assert response.status_code == 401


def test_signing_out_of_hop3_ends_the_apps_session(client, gated, account):
    gated()
    account("mia", Role.MEMBER)
    cookie = gate_cookie_for(client, "mia")
    admin_session = client.cookies.get(AUTH_COOKIE)

    client.cookies.set(AUTH_COOKIE, admin_session)
    client.post("/auth/logout", follow_redirects=False)

    assert check(client, cookie=f"{GATE_COOKIE}={cookie}").status_code == 401


def test_a_foreign_next_is_not_followed(client, gated, account):
    gated()
    account("mia", Role.MEMBER)

    response = sign_in(client, "mia", "https://evil.example.com/steal")

    assert response.headers["location"] == "/auth/profile"


def test_a_code_is_single_use_and_bound_to_its_app(client, gated, account):
    gated()
    gated(name="wiki", host="wiki.example.org")
    account("mia", Role.MEMBER)
    target = urlsplit(sign_in(client, "mia", f"https://{HOST}/").headers["location"])
    callback = f"{target.path}?{target.query}"

    elsewhere = client.get(callback, headers={"X-Hop3-App": "wiki"})
    replayed = client.get(callback, headers={"X-Hop3-App": "notes"})

    assert elsewhere.status_code == 400
    assert replayed.status_code == 400  # the wrong app's attempt spent it


def test_a_signed_in_session_crosses_without_a_form(client, gated, account):
    gated()
    account("mia", Role.MEMBER)
    sign_in(client, "mia", "")

    response = client.get(
        f"/auth/login?next=https://{HOST}/page", follow_redirects=False
    )

    assert urlsplit(response.headers["location"]).path == "/_hop3/auth/callback"


def test_an_app_without_a_gate_fails_closed(client):
    assert check(client, app="nothing").status_code == 503


def test_a_gate_cookie_is_not_an_api_token():
    token = gate_token(Grant("notes", "mia", "session-id", 2_000_000_000))

    assert validate_token(token) is None


def test_the_next_field_is_escaped(client):
    page = client.get('/auth/login?next="><script>alert(1)</script>')

    assert "<script>alert(1)" not in page.text
