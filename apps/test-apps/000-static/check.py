#!/usr/bin/env python3

"""
Check if the app is up and running.

This is specific to the testing harness.
"""

import sys

import httpx


def check(hostname, port):
    """Check if the static app is accessible.

    Args:
        hostname: The hostname/vhost to test
        port: The HTTP port to connect to
    """
    url = f"http://localhost:{port}/"
    response = httpx.get(url, headers={"Host": hostname}, verify=False)
    assert response.is_success, f"HTTP request failed with status {response.status_code}"
    assert "Hello World!" in response.text, f"Expected 'Hello World!' in response, got: {response.text}"


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        check(sys.argv[1], int(sys.argv[2]))
    else:
        # Legacy: just hostname for HTTPS
        url = f"https://{sys.argv[1]}/"
        response = httpx.get(url, verify=False)
        assert response.is_success
        assert "Hello World!" in response.text
