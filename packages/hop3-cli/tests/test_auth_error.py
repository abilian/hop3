# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test authentication error messages."""

from __future__ import annotations

from unittest.mock import Mock, patch

from hop3_cli.config import Config
from hop3_cli.rpc import Client
from jsonrpcclient import Error


def _make_config(api_url: str = "http://localhost:8000") -> Config:
    """Create a Config with context-based configuration."""
    return Config(
        data={
            "contexts": {"default": {"api_url": api_url, "api_token": ""}},
            "current_context": "default",
        }
    )


def test_401_error_message():
    """Test that 401 errors return a helpful message."""
    config = _make_config()
    client = Client(config=config)

    # Mock the requests.post to return a 401 response
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.json.return_value = {}

    with patch("hop3_cli.rpc.client.requests.post", return_value=mock_response):
        response = client.rpc("cli", ["auth"])

    # Check that we got an Error response
    assert isinstance(response, Error)
    assert response.code == 401

    # Check that the error message is helpful
    assert "Authentication required" in response.message
    assert "hop auth:login" in response.message
    assert "hop auth:register" in response.message
    assert "config.toml" in response.message or "HOP3_API_TOKEN" in response.message


def test_other_http_errors():
    """Test that other HTTP errors are handled properly."""
    config = _make_config()
    client = Client(config=config)

    # Mock the requests.post to return a 500 response
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.json.return_value = {}
    mock_response.raise_for_status.side_effect = Exception("Internal Server Error")

    with patch("hop3_cli.rpc.client.requests.post", return_value=mock_response):
        response = client.rpc("cli", ["auth"])

    # Check that we got an Error response
    assert isinstance(response, Error)
    assert response.code == 500


def test_jsonrpc_error_with_http_404():
    """Test that JSON-RPC errors returned with HTTP 404 are parsed correctly.

    The server returns HTTP 404 with a JSON-RPC error body for "command not found".
    The client should extract the clean error message, not show the HTTP error.
    """
    config = _make_config()
    client = Client(config=config)

    # Mock the requests.post to return a 404 with JSON-RPC error body
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.ok = False
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "error": {
            "code": -32601,
            "message": "Command 'xxx' not found",
        },
        "id": 1,
    }

    with patch("hop3_cli.rpc.client.requests.post", return_value=mock_response):
        response = client.rpc("cli", ["xxx"])

    # Check that we got an Error response with the clean message
    assert isinstance(response, Error)
    assert response.code == -32601
    assert response.message == "Command 'xxx' not found"
    # Should NOT contain HTTP 404 error text
    assert "HTTP" not in response.message
    assert "404" not in response.message


def test_jsonrpc_error_with_data_field():
    """Test that JSON-RPC error data field is preserved."""
    config = _make_config()
    client = Client(config=config)

    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.ok = False
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "error": {
            "code": -32602,
            "message": "Invalid params",
            "data": "Missing required parameter 'app_name'",
        },
        "id": 1,
    }

    with patch("hop3_cli.rpc.client.requests.post", return_value=mock_response):
        response = client.rpc("cli", ["app:start"])

    assert isinstance(response, Error)
    assert response.code == -32602
    assert response.message == "Invalid params"
    assert response.data == "Missing required parameter 'app_name'"
