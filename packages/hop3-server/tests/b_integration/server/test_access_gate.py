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
from hop3.server.security.access_gate import (
    GATE_COOKIE,
    STATE_COOKIE,
    Grant,
    gate_token,
)
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


def start_sign_in(client, *, app="notes", host=HOST, uri="/page") -> tuple[str, str]:
    """What the gate does for an anonymous browser: ``(next, state)``."""
    refused = check(client, app=app, host=host, uri=uri)
    assert refused.status_code == 401
    query = parse_qs(urlsplit(refused.headers["x-hop3-login"]).query)
    state_cookie = refused.headers["x-hop3-state"]
    assert state_cookie.startswith(f"{STATE_COOKIE}=")
    state = state_cookie.split(";", 1)[0].split("=", 1)[1]
    assert query["state"] == [state]
    return query["next"][0], state


def sign_in(client, username, next_url="", state=""):
    """Sign in on the admin domain; the redirect it answers with."""
    return client.post(
        "/auth/login",
        data={
            "username": username,
            "password": "password123",
            "next": next_url,
            "state": state,
        },
        follow_redirects=False,
    )


def redeem(client, callback_url, *, app="notes", state=""):
    """The callback on the app's host, from a browser holding ``state``."""
    target = urlsplit(callback_url)
    headers = {"X-Hop3-App": app}
    if state:
        headers["Cookie"] = f"{STATE_COOKIE}={state}"
    client.cookies.clear()
    return client.get(
        f"{target.path}?{target.query}", headers=headers, follow_redirects=False
    )


def gate_cookie_for(client, username, app="notes", host=HOST, next_path="/page"):
    """Run the handshake a browser runs; the gate cookie the app's host gets."""
    next_url, state = start_sign_in(client, app=app, host=host, uri=next_path)
    handoff = sign_in(client, username, next_url, state)
    target = urlsplit(handoff.headers["location"])
    assert (target.netloc, target.path) == (host, "/_hop3/auth/callback")
    callback = redeem(client, handoff.headers["location"], app=app, state=state)
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
    next_url, state = start_sign_in(client)
    callback = sign_in(client, "mia", next_url, state).headers["location"]
    admin_session = client.cookies.get(AUTH_COOKIE)
    set_cookie = redeem(client, callback, state=state).headers["set-cookie"]
    cookie = set_cookie.split(";", 1)[0].split("=", 1)[1]

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
    next_url, state = start_sign_in(client, uri="/")
    callback = sign_in(client, "mia", next_url, state).headers["location"]

    elsewhere = redeem(client, callback, app="wiki", state=state)
    replayed = redeem(client, callback, app="notes", state=state)

    assert elsewhere.status_code == 400
    assert replayed.status_code == 400  # the wrong app's attempt spent it


def test_a_code_is_refused_in_a_browser_that_did_not_start_the_sign_in(
    client, gated, account
):
    """Login CSRF: an attacker's code, opened in the victim's browser."""
    gated()
    account("mallory", Role.MEMBER)
    next_url, attacker_state = start_sign_in(client)
    callback = sign_in(client, "mallory", next_url, attacker_state).headers["location"]
    _, victim_state = start_sign_in(client)

    without_state = redeem(client, callback)
    with_its_own_state = redeem(client, callback, state=victim_state)

    assert without_state.status_code == 400
    assert with_its_own_state.status_code == 400


def test_a_signed_in_session_crosses_without_a_form(client, gated, account):
    gated()
    account("mia", Role.MEMBER)
    next_url, state = start_sign_in(client)
    sign_in(client, "mia")

    response = client.get(
        "/auth/login",
        params={"next": next_url, "state": state},
        follow_redirects=False,
    )

    assert urlsplit(response.headers["location"]).path == "/_hop3/auth/callback"


def test_a_sign_in_that_did_not_start_at_the_gate_goes_back_to_it(
    client, gated, account
):
    """No state means no browser to bind a code to: let the gate start over."""
    gated()
    account("mia", Role.MEMBER)
    sign_in(client, "mia")

    response = client.get(
        "/auth/login", params={"next": f"https://{HOST}/page"}, follow_redirects=False
    )

    assert response.headers["location"] == f"https://{HOST}/page"


def test_an_app_without_a_gate_fails_closed(client):
    assert check(client, app="nothing").status_code == 503


def test_a_gate_cookie_is_not_an_api_token():
    token = gate_token(Grant("notes", "mia", "session-id", 2_000_000_000, "state"))

    assert validate_token(token) is None


def test_the_next_field_is_escaped(client):
    page = client.get('/auth/login?next="><script>alert(1)</script>')

    assert "<script>alert(1)" not in page.text
