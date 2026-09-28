# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The access gate through the server's own proxy and admin domain (ADR 062).

The gate's e2e runs in a container with a stand-in admin domain. This runs
wherever the fixture is deployed: an anonymous request is sent to the Hop3
sign-in on the admin domain, that page answers, a public path is served, and an
identity header a client forges reaches neither the gate nor the app.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from hop3.server.checks import Check, run

FORGED = {"X-Hop3-User": "admin", "X-Hop3-Role": "admin"}


def check(c: Check) -> None:
    c.step("an anonymous request is sent to sign in")
    response = c.expect_status(c.get("/"), 302)
    target = response.headers.get("location", "")
    login = urlsplit(target)
    query = parse_qs(login.query)
    c.expect(
        login.scheme == "https" and login.path == "/auth/login",
        f"redirected to {target!r}, not to the Hop3 sign-in",
    )
    c.expect(
        query.get("next") == [f"https://{c.host}/"],
        f"the sign-in would not come back to this app: next={query.get('next')}",
    )
    c.expect(
        query.get("state")
        and "__Host-hop3_state=" in response.headers.get("set-cookie", ""),
        "the sign-in is not bound to this browser (no state, or no state cookie)",
    )

    c.step("the sign-in page answers on the admin domain")
    admin = Check(login.hostname or "", c.port)
    page = admin.expect_status(admin.get(f"{login.path}?{login.query}"), 200)
    admin.expect(
        'name="password"' in page.text, "the admin domain served no sign-in form"
    )

    c.step("a public path is served, and a forged identity is dropped")
    page = c.expect_status(c.get("/public/ping", headers=FORGED), 200)
    c.expect(
        page.text == "GATED APP PUBLIC: user=-",
        f"the public page, or the identity the app received, is wrong: {page.text[:200]!r}",
    )

    c.step("a forged identity does not pass the gate")
    c.expect_status(c.get("/", headers=FORGED), 302)


run(check)
