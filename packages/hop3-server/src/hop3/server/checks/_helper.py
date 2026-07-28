# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Support library for an app's ``check.py``, uploaded beside it and run ON the server.

Every app's smoke test is a plain Python script, so it can express whatever that
app actually needs — a form login, HTTP Basic, a socket.io handshake, or a
sequence of authenticated actions after signing in. This module exists so those
scripts stay *similar*: same entry point, same request plumbing, same failure
wording, same exit codes. Only the app-specific steps differ.

A script looks like::

    from hop3.server.checks import run

    def check(c):
        c.step("sign in")
        page = c.get("/login")
        token = c.extract(page, r'name="_token" value="([^"]+)"')
        form_data = {
            "email": c.admin.email,
            "password": c.admin.password,
            "_token": token,
        }
        c.post("/login", form_data)
        c.expect_signed_in("/", contains="Dashboard")

        c.step("a wrong password is refused")
        c.expect_sign_in_refused(...)

    run(check)

Failure is always loud and specific: every helper says what it expected, what it
got, and which step it was on. A check that cannot run (no credentials, missing
token) FAILS — it never degrades into a weaker assertion, because a smoke test
that quietly tests less than it claims is worse than none.
"""

from __future__ import annotations

import os
import re
import sys
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable

TIMEOUT = 30.0


class CheckError(Exception):
    """An expectation did not hold. Carries an operator-readable explanation."""


@dataclass(frozen=True)
class Admin:
    """The credential Hop3 generated for this app (ADR 056)."""

    username: str
    email: str
    password: str

    @property
    def identity(self) -> str:
        """Whichever identifier the app signs in with, preferring the username."""
        return self.username or self.email


class Check:
    """
    One app's smoke-test session: a client bound to the app's vhost.

    Requests go to ``http://localhost:<port>`` with a ``Host`` header, because
    the script runs on the server where that reaches nginx and selects this
    app's vhost. Cookies persist across calls, so a sign-in carries into the
    requests that follow it.
    """

    def __init__(self, host: str, port: int = 443) -> None:
        self.host = host
        self.port = port
        # HTTPS, always — even though the harness passes port 80 for historical
        # reasons. Two reasons this is not a preference:
        #   1. Hop3 redirects HTTP to HTTPS by default, so a plain-HTTP check
        #      would be testing the redirect rather than the app.
        #   2. An app served over HTTPS issues Secure session cookies, which a
        #      client never sends back over HTTP — so a sign-in over HTTP fails
        #      no matter how correct the credential is. Testing there would
        #      report every app as broken.
        # The certificate is not verified: these are self-signed or per-host
        # certs and the connection never leaves the server (localhost).
        self.base_url = "https://localhost:443"
        #: The step being attempted; failures quote it so a report says where.
        self.current_step = "starting"
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Host": host},
            timeout=TIMEOUT,
            verify=False,
            follow_redirects=False,
        )

    # -- credentials ------------------------------------------------------

    @property
    def admin(self) -> Admin:
        """
        The app's generated admin credential, or FAIL.

        The harness injects these; their absence means the app declares no
        ``[admin]`` or the credential was never provisioned. Either way the
        login cannot be tested, and saying so beats passing a test that never
        signed in.
        """
        password = os.environ.get("HOP3_ADMIN_PASSWORD", "")
        if not password:
            msg = (
                "no admin credential was provided (HOP3_ADMIN_PASSWORD is unset), "
                "so the sign-in cannot be tested. Declare [admin] in hop3.toml, or "
                "check that the credential was provisioned for this app."
            )
            raise CheckError(msg)
        return Admin(
            username=os.environ.get("HOP3_ADMIN_USER", ""),
            email=os.environ.get("HOP3_ADMIN_EMAIL", ""),
            password=password,
        )

    # -- narration --------------------------------------------------------

    def step(self, name: str) -> None:
        """Name the step being attempted; failures quote it."""
        self.current_step = name
        print(f"  - {name}", flush=True)

    # -- requests ---------------------------------------------------------

    def get(self, path: str, **kwargs: object) -> httpx.Response:
        return self._request("GET", path, **kwargs)

    def post(
        self, path: str, data: dict | None = None, **kwargs: object
    ) -> httpx.Response:
        return self._request("POST", path, data=data, **kwargs)

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        # Over TLS the Host header alone does not select the vhost: nginx picks
        # the certificate (and therefore the server block) from the SNI name,
        # which would be "localhost" and land on the platform's default vhost —
        # a 404 for every app. Send the app's hostname as SNI while still
        # connecting to loopback, so no DNS is needed and no traffic leaves the
        # server.
        kwargs.setdefault("extensions", {"sni_hostname": self.host})
        try:
            return self.client.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            msg = f"{method} {path} failed to complete: {e}"
            raise CheckError(msg) from e

    # -- extraction -------------------------------------------------------

    def extract(
        self, source: httpx.Response | str, pattern: str, what: str = "token"
    ) -> str:
        """
        Pull the first capture group of ``pattern`` out of a response body.

        Used for CSRF tokens, which nearly every form login requires. A missing
        one FAILS rather than posting without it: an empty token turns a real
        credential check into a token-rejection, which looks identical from the
        outside and would hide a genuine sign-in failure.
        """
        text = source.text if isinstance(source, httpx.Response) else source
        match = re.search(pattern, text)
        if not match:
            msg = (
                f"could not find the {what} in the page (pattern {pattern!r}). "
                f"The page may be an error or install screen rather than the "
                f"expected form; it began: {text[:200]!r}"
            )
            raise CheckError(msg)
        return match.group(1)

    # -- expectations -----------------------------------------------------

    def expect(self, condition: object, message: str) -> None:
        """Assert an app-specific condition, with an explanation on failure."""
        if not condition:
            raise CheckError(message)

    def expect_status(self, response: httpx.Response, *allowed: int) -> httpx.Response:
        if response.status_code not in allowed:
            expected = " or ".join(str(code) for code in allowed)
            msg = (
                f"{response.request.method} {response.request.url.path} returned "
                f"{response.status_code}, expected {expected}"
            )
            raise CheckError(msg)
        return response

    def expect_signed_in(self, path: str, contains: str) -> httpx.Response:
        """
        Prove the session is real by fetching a page only a signed-in user sees.

        This is the assertion that matters. A sign-in POST returning a redirect
        proves very little — apps redirect back to the login form on failure
        too — so the test is whether the session cookies now reach authenticated
        content. ``contains`` must be something that appears ONLY when signed in
        (a logout link, the account name), never the app's title.
        """
        response = self.client.get(
            path,
            follow_redirects=True,
            extensions={"sni_hostname": self.host},
        )
        if response.status_code != 200:
            msg = (
                f"signed-in page {path} returned {response.status_code}, not 200 — "
                f"the sign-in did not establish a session"
            )
            raise CheckError(msg)
        if contains not in response.text:
            msg = (
                f"signed-in page {path} did not contain {contains!r}, so the "
                f"session is not authenticated. Landed on: "
                f"{response.url.path!r}, body began: {response.text[:200]!r}"
            )
            raise CheckError(msg)
        return response

    def expect_sign_in_refused(self, attempt: Callable[[Check], object]) -> None:
        """
        A deliberately wrong password must be REFUSED.

        Without this a smoke test cannot tell a working login from one that
        accepts anything, or from a success signal we have misread. ``attempt``
        is a callable performing the sign-in with a bad password and returning
        the response.
        """
        fresh = Check(self.host, self.port)
        fresh.current_step = self.current_step
        try:
            response = attempt(fresh)
        except CheckError:
            return  # refused before it could even post — still a refusal
        if 200 <= response.status_code < 400 and self._looks_authenticated(fresh):
            msg = (
                "a WRONG password was accepted — the sign-in check proves nothing "
                "about the real credential"
            )
            raise CheckError(msg)

    @staticmethod
    def _looks_authenticated(check: Check) -> bool:
        """Best-effort: did a bad-password attempt still yield a session?"""
        return any(
            "session" in cookie.lower() or "sess" in cookie.lower()
            for cookie in check.client.cookies
        )

    def close(self) -> None:
        self.client.close()


def run(check_fn: Callable[[Check], None]) -> None:
    """
    Entry point every ``check.py`` ends with: ``run(check)``.

    Parses the harness's ``<host> <port>`` arguments, runs the check, and maps
    the outcome to an exit code — 0 pass, 1 fail — printing an explanation the
    operator can act on without reading the script.
    """
    if len(sys.argv) < 2:
        print("usage: check.py <hostname> [port]", file=sys.stderr)
        sys.exit(2)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 443

    check = Check(host, port)
    print(f"check: {host} (via {check.base_url})", flush=True)
    try:
        check_fn(check)
    except CheckError as e:
        print(f"\nFAILED during '{check.current_step}': {e}", file=sys.stderr)
        sys.exit(1)
    except Exception:
        # An unexpected error is a failure, never a pass; show the traceback so
        # a broken check is distinguishable from a broken app.
        print(f"\nERROR during '{check.current_step}':", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        check.close()

    print("OK", flush=True)
    sys.exit(0)
