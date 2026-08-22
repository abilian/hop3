# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
A redirect from the RPC endpoint must be reported, not followed.

An unauthenticated call is answered with 302 to a login page. `requests`
follows redirects by default, so a 200 of HTML arrived instead — which parses
as neither JSON-RPC nor an HTTP error, and surfaced as the bare string
"Unexpected response format". No mention of authentication, nothing to act on.

A whole 34-app catalog run failed that way in under ten seconds and read like a
broken server: hours went into inspecting listening ports, supervisor state and
the installer before the per-app log turned out to say "Authentication
required" all along.

So: do not follow, and say what happened.
"""

from __future__ import annotations

from hop3_cli.rpc.client import Client


class _Response:
    """Enough of requests.Response for the parser."""

    def __init__(self, status_code: int, headers: dict | None = None, text: str = ""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def json(self):
        msg = "not json"
        raise ValueError(msg)

    def raise_for_status(self) -> None:
        return None


def _client() -> Client:
    """A Client with just enough wiring for URL formatting."""
    client = Client.__new__(Client)
    client.tunnel = None
    client.__dict__["api_url"] = "http://localhost:8000"  # cached_property
    return client


def test_a_redirect_names_authentication_as_the_likely_cause():
    client = _client()

    error = client._parse_response(_Response(302, {"Location": "/login"}), {"id": 1})

    assert "hop3 login" in error.message
    assert "/login" in error.message


def test_a_redirect_is_not_reported_as_a_parse_problem():
    """The old message blamed the response format for an auth failure."""
    client = _client()

    error = client._parse_response(_Response(302, {"Location": "/login"}), {"id": 1})

    assert "Unexpected response format" not in error.message


def test_an_unparseable_body_says_what_arrived():
    """
    "Unexpected response format" named no cause and suggested no next step.

    The status code and a snippet of the body are what let a reader tell an
    auth page from a proxy error from the wrong port.
    """
    client = _client()

    error = client._parse_response(
        _Response(200, text="<html>Sign in</html>"), {"id": 1}
    )

    assert "200" in error.message
    assert "Sign in" in error.message
