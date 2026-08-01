# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""X-Forwarded-For trust in client_ip (audit H1 — rate-limit bypass)."""

from __future__ import annotations

from dataclasses import dataclass

from hop3.server.security.proxy_headers import client_ip


@dataclass
class _FakeClient:
    host: str


class _FakeRequest:
    """Minimal stand-in exposing the .client / .headers client_ip reads."""

    def __init__(self, peer: str | None, xff: str | None = None) -> None:
        self.client = _FakeClient(peer) if peer else None
        self.headers = {} if xff is None else {"x-forwarded-for": xff}


def test_untrusted_peer_ignores_spoofed_xff():
    # The bypass: a direct client sets XFF to a fresh IP each request. The peer
    # is not a trusted proxy, so the header is ignored and the real peer wins.
    req = _FakeRequest(peer="203.0.113.7", xff="1.2.3.4")
    assert client_ip(req) == "203.0.113.7"


def test_trusted_peer_uses_appended_rightmost_xff():
    # Behind nginx (loopback peer). $proxy_add_x_forwarded_for appends the real
    # client on the right; a client-spoofed leftmost must not win.
    req = _FakeRequest(peer="127.0.0.1", xff="1.2.3.4, 203.0.113.9")
    assert client_ip(req) == "203.0.113.9"


def test_trusted_peer_no_xff_falls_back_to_peer():
    req = _FakeRequest(peer="127.0.0.1")
    assert client_ip(req) == "127.0.0.1"


def test_missing_client_is_unknown():
    req = _FakeRequest(peer=None)
    assert client_ip(req) == "unknown"


def test_configured_trusted_proxy_is_honored(monkeypatch):
    monkeypatch.setenv("HOP3_TRUSTED_PROXIES", "10.0.0.5")
    req = _FakeRequest(peer="10.0.0.5", xff="1.2.3.4, 203.0.113.9")
    assert client_ip(req) == "203.0.113.9"
    # A different, non-configured proxy is still untrusted.
    other = _FakeRequest(peer="10.0.0.6", xff="1.2.3.4, 203.0.113.9")
    assert client_ip(other) == "10.0.0.6"
