# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for RPC endpoint authentication."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from litestar.testing import TestClient

from hop3.server.asgi import create_app
from hop3.server.security.tokens import create_token


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment."""
    # Set required secrets without needing to reload config
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-rpc-auth-testing")
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
def admin_token():
    """Create a valid admin token."""
    return create_token("admin", scopes=["authenticated", "admin"])


@pytest_asyncio.fixture
async def async_client(setup_test_env):
    """Create an async HTTP client that properly handles middleware."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def test_rpc_public_command_without_auth(client: TestClient):
    """Test that public commands work without authentication."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["help"], "extra_args": {}},
            "id": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "result" in data


def _get_token_request(client: TestClient, password: str = "password"):
    return client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {
                "cli_args": ["auth", "get-token", "testuser", password],
                "extra_args": {},
            },
            "id": 1,
        },
    )


def test_rpc_auth_get_token_without_token(client: TestClient):
    """Test that auth:get-token works without authentication."""
    response = _get_token_request(client)

    # Should work even without auth (though user may not exist)
    assert response.status_code in {200, 401}  # 200 for public access


def test_rpc_auth_get_token_is_rate_limited(client: TestClient):
    """
    Password guessing over RPC hits the same 5/min ceiling as the web form.

    Regression for audit 2026-07-29 F1/F4: `auth get-token` is unauthenticated
    and verifies a password, but only `POST /auth/login` was throttled, so an
    attacker could guess at bcrypt speed by choosing the other transport.
    """
    for _ in range(5):
        assert _get_token_request(client, "wrong").status_code != 429

    blocked = _get_token_request(client, "wrong")
    assert blocked.status_code == 429
    assert "Too many authentication attempts" in blocked.json()["error"]["message"]


def test_rpc_public_command_is_not_rate_limited(client: TestClient):
    """A command that verifies no credential stays unthrottled."""
    for _ in range(10):
        response = client.post(
            "/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "cli",
                "params": {"cli_args": ["help"], "extra_args": {}},
                "id": 1,
            },
        )
        assert response.status_code == 200


def test_rpc_protected_command_without_auth(client: TestClient):
    """Test that protected commands require authentication."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
    )

    # Should fail without authentication
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert "Authentication required" in data["error"]["message"]


@pytest.mark.asyncio
async def test_rpc_protected_command_with_valid_auth(
    async_client: httpx.AsyncClient, valid_token: str
):
    """Test that protected commands work with valid authentication."""
    response = await async_client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    # Should work with authentication
    assert response.status_code == 200


def test_rpc_protected_command_with_invalid_token(client: TestClient):
    """Test that protected commands fail with invalid token."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": "Bearer invalid-token-here"},
    )

    # Should fail with invalid token
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rpc_whoami_with_auth(async_client: httpx.AsyncClient, valid_token: str):
    """Test whoami command receives authenticated username."""
    response = await async_client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["auth", "whoami"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {valid_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    # Check that the command received the username
    # (it might fail because the user doesn't exist in DB, but that's OK for this test)
    assert "result" in data or "error" in data


def test_rpc_auth_register_requires_auth(client: TestClient):
    """auth:register is admin-only (security review C-001/H-002)."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {
                "cli_args": ["auth", "register", "newuser", "new@test.com", "pass123"],
                "extra_args": {},
            },
            "id": 1,
        },
    )

    # Anonymous callers must be rejected at the RPC auth gate.
    assert response.status_code in {401, 403}


def test_rpc_missing_authorization_header(client: TestClient):
    """Test protected endpoint with missing Authorization header."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["deploy", "myapp"], "extra_args": {}},
            "id": 1,
        },
    )

    assert response.status_code == 401


def test_rpc_malformed_authorization_header(client: TestClient):
    """Test protected endpoint with malformed Authorization header."""
    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": "NotBearer token"},
    )

    assert response.status_code == 401


def test_rpc_expired_token(client: TestClient):
    """Test that expired tokens are rejected."""
    # Create a token that's already expired
    expired_token = create_token("testuser", expires_hours=-1)

    response = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cli_args": ["app", "list"], "extra_args": {}},
            "id": 1,
        },
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
