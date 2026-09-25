# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The access gate's endpoints (ADR 062).

``/auth/check`` answers the proxy's forward-auth call on every request to a
gated app. The proxy names the app in ``X-Hop3-App`` and the original request
in ``X-Forwarded-Host`` and ``X-Forwarded-Uri``, overwriting whatever the
client sent. The answer:

- 200 admits the request. ``X-Hop3-User`` and ``X-Hop3-Role`` say who is
  asking (absent when nobody signed in, on a public path), and ``Cookie`` is
  the request's cookies without the gate cookie. The proxy replaces the
  request's headers of those names with these, deleting the ones absent here,
  so the app can trust them and never sees a Hop3 credential.
- 401, or 302 with ``?redirect=1``, sends the browser to sign in, and sets
  the state cookie that binds the sign-in to this browser. nginx's
  ``auth_request`` understands only 2xx, 401 and 403, so it redirects on 401
  itself and sets the cookie from ``X-Hop3-State``; Caddy and Traefik pass the
  check's own response, cookie included, to the client.
- 403 says the account's role is too low.

``/_hop3/auth/callback`` is routed to hop3-server on the app's own host, so it
can set the gate cookie there.
"""

from __future__ import annotations

import time

from litestar import Controller, Request, get
from litestar.datastructures import Cookie
from litestar.response import Redirect, Response

from hop3.server.security.access_gate import (
    GATE_COOKIE,
    STATE_COOKIE,
    STATE_LIFETIME_SECONDS,
    Admit,
    Forbid,
    SignIn,
    account_for,
    decide,
    gate_token,
    load_policy,
    new_state,
    redeem_code,
    same_host_path,
    sign_in_url,
    split_gate_cookie,
)

APP_HEADER = "x-hop3-app"
NO_STORE = {"Cache-Control": "no-store"}


class AccessGateController(Controller):
    """Forward-auth check and sign-in callback for gated apps."""

    path = "/"

    @get("/auth/check", sync_to_thread=True)
    def check(self, request: Request) -> Response:
        """Admit, send to sign-in, or refuse one request to a gated app."""
        app_name = request.headers.get(APP_HEADER, "")
        policy = load_policy(app_name)
        if policy is None:
            # A proxy config naming an app with no gate is stale or forged.
            # Fail closed, loudly: the operator sees a 503, not an open app.
            return Response(
                content=f"The access gate has no policy for app {app_name!r}; "
                f"redeploy the app.",
                status_code=503,
                media_type="text/plain",
                headers=NO_STORE,
            )

        request_uri = request.headers.get("x-forwarded-uri", "/")
        cookies = "; ".join(request.headers.getall("cookie", []))
        gate_cookie, other_cookies = split_gate_cookie(cookies)
        verdict = decide(policy, request_uri, account_for(gate_cookie, app_name))

        match verdict:
            case Admit(account=account):
                headers = dict(NO_STORE)
                if account is not None:
                    headers["X-Hop3-User"] = account.username
                    headers["X-Hop3-Role"] = account.role.value
                if other_cookies:
                    headers["Cookie"] = other_cookies
                return Response(content="", status_code=200, headers=headers)
            case Forbid(account=account):
                return Response(
                    content=f"This app needs the {policy.role.value} role; "
                    f"account '{account.username}' is {account.role.value}. "
                    f"An admin can grant it: hop3 user set-role "
                    f"{account.username} {policy.role.value}",
                    status_code=403,
                    media_type="text/plain",
                    headers=NO_STORE,
                )
            case SignIn():
                host = request.headers.get("x-forwarded-host", "")
                state = new_state()
                target = sign_in_url(host, request_uri, state)
                cookie = _host_cookie(STATE_COOKIE, state, STATE_LIFETIME_SECONDS)
                if request.query_params.get("redirect"):
                    return Redirect(
                        path=target, status_code=302, cookies=[cookie], headers=NO_STORE
                    )
                return Response(
                    content="",
                    status_code=401,
                    headers={
                        **NO_STORE,
                        "X-Hop3-Login": target,
                        "X-Hop3-State": cookie.to_header(header=""),
                    },
                )

    @get("/_hop3/auth/callback", sync_to_thread=False)
    def callback(self, request: Request) -> Response:
        """Redeem a one-time code on the app's host and set its gate cookie."""
        app_name = request.headers.get(APP_HEADER, "")
        grant = redeem_code(
            request.query_params.get("code", ""),
            app_name,
            request.cookies.get(STATE_COOKIE, ""),
        )
        if grant is None:
            return Response(
                content="This sign-in link has expired, was already used, or was "
                "started in another browser. Reload the page to sign in again.",
                status_code=400,
                media_type="text/plain",
                headers=NO_STORE,
            )
        gate = _host_cookie(
            GATE_COOKIE,
            gate_token(grant),
            max(0, grant.expires_at - int(time.time())),
        )
        spent_state = _host_cookie(STATE_COOKIE, "", 0)
        return Redirect(
            path=same_host_path(request.query_params.get("next", "/")),
            cookies=[gate, spent_state],
            # The code is spent, but keep it out of the next page's Referer.
            headers={**NO_STORE, "Referrer-Policy": "no-referrer"},
        )


def _host_cookie(name: str, value: str, max_age: int) -> Cookie:
    """A ``__Host-`` cookie: Secure, host-only, for the whole host."""
    return Cookie(
        key=name,
        value=value,
        max_age=max_age,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
