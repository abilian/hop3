# Copyright (c) 2025, Abilian SAS
"""Test authentication error messages."""

from __future__ import annotations

from unittest.mock import Mock, patch

from hop3_cli.client import Client
from hop3_cli.config import Config
from jsonrpcclient import Error


def test_401_error_message():
    """Test that 401 errors return a helpful message."""
    config = Config(data={"api_url": "http://localhost:8000"})
    client = Client(config=config, state=None)

    # Mock the requests.post to return a 401 response
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.json.return_value = {}

    with patch("hop3_cli.client.requests.post", return_value=mock_response):
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
    config = Config(data={"api_url": "http://localhost:8000"})
    client = Client(config=config, state=None)

    # Mock the requests.post to return a 500 response
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.json.return_value = {}
    mock_response.raise_for_status.side_effect = Exception("Internal Server Error")

    with patch("hop3_cli.client.requests.post", return_value=mock_response):
        response = client.rpc("cli", ["auth"])

    # Check that we got an Error response
    assert isinstance(response, Error)
    assert response.code == 500
