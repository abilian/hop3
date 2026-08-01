# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
What the reverse proxy tells us about a request, and when to believe it.

`X-Forwarded-For` and `X-Forwarded-Proto` are just request headers: any client
can send them. They are trustworthy only when the TCP peer is a proxy we put
there. Every consumer of a forwarded header has to make that same trust
decision, so it is made once, here.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection

__all__ = ["client_ip", "request_is_secure"]

# TCP peers we trust to have set the X-Forwarded-* headers. hop3-server sits
# behind the platform reverse proxy (nginx) on the same host; a client
# connecting directly to the app port is never trusted to set them. Additional
# proxy IPs (e.g. an external load balancer) can be allow-listed via
# HOP3_TRUSTED_PROXIES.
_DEFAULT_TRUSTED_PROXIES: frozenset[str] = frozenset({"127.0.0.1", "::1"})


def _trusted_proxies() -> frozenset[str]:
    extra = os.environ.get("HOP3_TRUSTED_PROXIES", "")
    if not extra:
        return _DEFAULT_TRUSTED_PROXIES
    return _DEFAULT_TRUSTED_PROXIES | {
        ip.strip() for ip in extra.split(",") if ip.strip()
    }


def _peer_is_trusted(connection: ASGIConnection) -> bool:
    peer = connection.client.host if connection.client else "unknown"
    return peer in _trusted_proxies()


def client_ip(connection: ASGIConnection) -> str:
    """
    Client IP for rate limiting (audit H1, CWE-290).

    X-Forwarded-For is honored ONLY when the TCP peer is a trusted proxy
    (loopback by default; extend with HOP3_TRUSTED_PROXIES). Otherwise the
    header is fully client-controlled, so an unauthenticated attacker could
    send a fresh IP per request and cycle past the per-IP rate limiter.

    When the peer IS trusted, we take the *rightmost* XFF entry — the address
    our proxy appended ($proxy_add_x_forwarded_for) — not the leftmost, which a
    client can pre-seed with a spoofed value before the proxy appends the real
    peer.
    """
    peer = connection.client.host if connection.client else "unknown"
    if _peer_is_trusted(connection):
        forwarded = connection.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return peer


def request_is_secure(connection: ASGIConnection) -> bool:
    """
    Whether the *browser* reached us over TLS.

    The ASGI scheme alone is wrong behind the platform's nginx, which
    terminates TLS and forwards over plain HTTP — every request would look
    insecure. `X-Forwarded-Proto` carries the browser's real scheme, and is
    believed on the same terms as `X-Forwarded-For`: only from a trusted peer.
    An untrusted client claiming `https` gets ignored, so the answer degrades
    to "not secure", which is the safe direction for every caller.
    """
    if _peer_is_trusted(connection):
        forwarded_proto = connection.headers.get("x-forwarded-proto", "")
        if forwarded_proto:
            return forwarded_proto.split(",")[-1].strip().lower() == "https"
    return connection.url.scheme in {"https", "wss"}
