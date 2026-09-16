#!/usr/bin/env python3

"""
Check that a php-fpm pool — not PHP's development server — served this app.

This is specific to the testing harness.
"""

from __future__ import annotations

import sys

import httpx


def check(hostname: str, port: int = 443) -> None:
    """Check that the app is served by php-fpm behind nginx.

    Args:
        hostname: Virtual host name (e.g., 'app.test.local')
        port: HTTPS port to connect to (default: 443)
    """
    response = httpx.get(
        f"https://localhost:{port}/",
        headers={"Host": hostname},
        verify=False,
        timeout=5.0,
        follow_redirects=True,
    )
    assert response.is_success, f"Expected success, got {response.status_code}"

    # The interpreter's own account of how it was invoked. `cli-server` here
    # would mean the app is still on PHP's single-threaded development server,
    # which is the whole thing the php-fpm runtime replaced — and a status code
    # cannot tell the two apart, because both answer 200.
    assert "fpm-fcgi" in response.text, (
        f"not served by php-fpm: {response.text[:200]!r}"
    )


if __name__ == "__main__":
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 443
    check(sys.argv[1], port)
