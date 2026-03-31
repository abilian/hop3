#!/usr/bin/env python3

"""
Check if the app is up and running.

This is specific to the testing harness.
"""
from __future__ import annotations

import sys

import httpx


def check(hostname: str, port: int = 443) -> None:
    """Check if the Flask app is serving correctly.

    Args:
        hostname: Virtual host name (e.g., 'app.test.local')
        port: HTTP port to connect to (default: 443)
    """
    url = f"http://localhost:{port}/"
    response = httpx.get(
        url,
        headers={"Host": hostname},
        verify=False,
        timeout=5.0,
        follow_redirects=True,
    )
    assert response.is_success, f"Expected success, got {response.status_code}"
    assert "Hello World!" in response.text, f"Unexpected content: {response.text[:100]}"


if __name__ == "__main__":
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 443
    check(sys.argv[1], port)
