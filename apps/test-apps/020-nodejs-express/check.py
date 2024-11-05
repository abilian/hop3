#!/usr/bin/env python3

"""
Check if the app is up and running.

This is specific to the testing harness.
"""
from __future__ import annotations

import sys

import httpx


def check(hostname) -> None:
    url = f"https://{hostname}/"
    response = httpx.get(url, verify=False)
    assert response.is_success
    assert "Hello World" in response.text


if __name__ == "__main__":
    check(sys.argv[1])
