#!/usr/bin/env python3

"""
Check that nothing above the document root is reachable.

This is specific to the testing harness.
"""

from __future__ import annotations

import sys

import httpx

#: The string planted in `.env`, one level above the document root. It is not a
#: credential; it is the thing that must never come back over HTTP.
CANARY = "canary-3f9a1c-must-never-be-served"

#: Paths a misresolved document root would expose. `/.env` is the one that
#: matters; the traversal forms are there because a document root is only as
#: good as the request normalisation in front of it.
ABOVE_THE_ROOT = ("/.env", "/../.env", "/%2e%2e/.env", "/..%2f.env", "/hop3.toml")


def check(hostname: str, port: int = 443) -> None:
    """Check the app serves from public/ and nothing above it.

    Args:
        hostname: Virtual host name (e.g., 'app.test.local')
        port: HTTPS port to connect to (default: 443)
    """
    client = httpx.Client(
        base_url=f"https://localhost:{port}",
        headers={"Host": hostname},
        verify=False,
        timeout=5.0,
        follow_redirects=True,
    )
    with client:
        home = client.get("/")
        assert home.is_success, f"Expected success, got {home.status_code}"
        assert "Served from public/" in home.text, (
            f"not the app's own page: {home.text[:200]!r}"
        )
        assert "fpm-fcgi" in home.text, f"not served by php-fpm: {home.text[:200]!r}"

        for path in ABOVE_THE_ROOT:
            # A 404 is fine, the app's own page is fine, an error is fine. The
            # only unacceptable answer is the content of a file beside the
            # document root, whatever status it arrives with.
            body = client.get(path).text
            assert CANARY not in body, (
                f"{path} served a file above the document root: the document "
                f"root resolved to the project directory, so this app's .env "
                f"is public"
            )


if __name__ == "__main__":
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 443
    check(sys.argv[1], port)
