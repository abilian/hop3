# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A `Secure` cookie over plain HTTP must fail loud, not loop.

Outside debug mode the auth cookie is `Secure`, so a browser on `http://`
accepts the `Set-Cookie` and never sends it back: login "succeeds", the
dashboard finds no credential, and bounces to the login page forever with no
error anywhere. Known since May 2026 (security-model.md §3.7).

`request_is_secure` decides the transport, and `cookie_would_be_dropped`
pairs it with the debug flag to name the one broken combination.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.server.security.proxy_headers import request_is_secure
from hop3.server.security.web_auth import cookie_would_be_dropped


def _conn(scheme: str = "http", *, peer: str = "203.0.113.5", **headers):
    return SimpleNamespace(
        url=SimpleNamespace(scheme=scheme),
        client=SimpleNamespace(host=peer),
        headers=headers,
    )


def test_plain_http_from_an_untrusted_peer_is_insecure() -> None:
    assert not request_is_secure(_conn("http"))


def test_direct_tls_is_secure() -> None:
    assert request_is_secure(_conn("https"))


def test_trusted_proxy_reporting_https_is_secure() -> None:
    """The platform's nginx terminates TLS and forwards plain HTTP."""
    conn = _conn("http", peer="127.0.0.1", **{"x-forwarded-proto": "https"})
    assert request_is_secure(conn)


def test_untrusted_client_cannot_claim_https() -> None:
    """
    Otherwise anyone could silence the warning by sending a header.

    The same reasoning as `client_ip`: a forwarded header is a claim, and only
    a peer we put there is allowed to make it.
    """
    conn = _conn("http", peer="203.0.113.5", **{"x-forwarded-proto": "https"})
    assert not request_is_secure(conn)


def test_rightmost_forwarded_proto_wins() -> None:
    """A client can pre-seed the header before our proxy appends to it."""
    conn = _conn("http", peer="127.0.0.1", **{"x-forwarded-proto": "https, http"})
    assert not request_is_secure(conn)


@pytest.mark.parametrize(
    ("debug", "scheme", "dropped"),
    [
        (False, "http", True),  # the broken pairing
        (False, "https", False),
        (True, "http", False),  # debug: cookie isn't Secure, so http works
        (True, "https", False),
    ],
)
def test_cookie_would_be_dropped(monkeypatch, debug, scheme, dropped) -> None:
    monkeypatch.setattr("hop3.server.security.web_auth.HOP3_DEBUG", debug)
    assert cookie_would_be_dropped(_conn(scheme)) is dropped
