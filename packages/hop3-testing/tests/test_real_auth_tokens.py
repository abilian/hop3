# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Real-auth test tokens — the harness authenticates instead of bypassing.

The harness no longer sets ``HOP3_UNSAFE`` to disable authentication; it mints a
JWT signed with the key the target server actually validates with. These tests
cover the two load-bearing pieces: signing with a chosen key, and reading the
server's key (fail-loud, no silent fallback to a key the server would reject).
"""

from __future__ import annotations

from types import SimpleNamespace

import jwt
import pytest
from hop3_testing.exceptions import ConfigurationError
from hop3_testing.targets.constants import E2E_TEST_SECRET_KEY, create_test_token
from hop3_testing.targets.helpers import read_server_secret_key


def test_token_is_signed_with_the_given_key():
    """A token signed with a server's key validates with that key — and a
    default-key token does NOT (which is exactly why the remote path needs the
    server's real key, not the E2E default)."""
    token = create_test_token(secret_key="server-real-key")
    decoded = jwt.decode(token, "server-real-key", algorithms=["HS256"])
    assert decoded["sub"]
    assert "admin" in decoded["scopes"]

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, E2E_TEST_SECRET_KEY, algorithms=["HS256"])


def test_default_key_is_the_e2e_key():
    """Docker keeps the E2E default (its server runs with that key)."""
    token = create_test_token()
    jwt.decode(token, E2E_TEST_SECRET_KEY, algorithms=["HS256"])  # no raise


def _backend(stdout: str):
    """A minimal stand-in for a CommandRunner: .run() returns an object with
    the captured stdout."""
    return SimpleNamespace(run=lambda cmd, check=False: SimpleNamespace(stdout=stdout))


def test_read_server_secret_key_returns_trimmed_key():
    key = read_server_secret_key(_backend('  "the-key"  \n'))
    assert key == "the-key"


def test_read_server_secret_key_fails_loud_when_absent():
    """No key on the box → abort, rather than fall back to a key the server
    would reject (which would surface later as an opaque 'Authentication
    required')."""
    with pytest.raises(ConfigurationError, match="signing key"):
        read_server_secret_key(_backend(""))
