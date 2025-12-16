# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Tests for API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from hop3_tui.api.client import Hop3Client, Hop3ClientError
from hop3_tui.api.models import AppState


class TestHop3Client:
    """Tests for Hop3Client."""

    def test_init_default(self):
        """Test default initialization."""
        client = Hop3Client()
        assert client.base_url == "http://localhost:5000"
        assert client.token is None

    def test_init_with_params(self):
        """Test initialization with parameters."""
        client = Hop3Client(
            base_url="https://hop3.example.com/",
            token="my-secret-token",
        )
        assert client.base_url == "https://hop3.example.com"
        assert client.token == "my-secret-token"

    def test_get_headers_without_token(self):
        """Test headers without token."""
        client = Hop3Client()
        headers = client._get_headers()
        assert headers == {"Content-Type": "application/json"}
        assert "Authorization" not in headers

    def test_get_headers_with_token(self):
        """Test headers with token."""
        client = Hop3Client(token="my-token")
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer my-token"

    def test_request_id_increments(self):
        """Test that request ID increments."""
        client = Hop3Client()
        id1 = client._next_request_id()
        id2 = client._next_request_id()
        id3 = client._next_request_id()

        assert id1 == 1
        assert id2 == 2
        assert id3 == 3


class TestHop3ClientAsync:
    """Async tests for Hop3Client."""

    @pytest.fixture
    def mock_httpx_client(self):
        """Create a mock httpx async client."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        return mock_client, mock_response

    @pytest.mark.asyncio
    async def test_list_apps_success(self, mock_httpx_client):
        """Test listing apps with successful response."""
        mock_client, mock_response = mock_httpx_client
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {
                "t": "table",
                "headers": ["NAME", "STATUS", "PORT"],
                "rows": [
                    ["myapp", "RUNNING", "8000"],
                    ["api", "STOPPED", None],
                ],
            },
            "id": 1,
        }

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_class.return_value.__aexit__ = AsyncMock(return_value=None)

            client = Hop3Client()
            apps = await client.list_apps()

            assert len(apps) == 2
            assert apps[0].name == "myapp"
            assert apps[0].state == AppState.RUNNING
            assert apps[0].port == 8000
            assert apps[1].name == "api"
            assert apps[1].state == AppState.STOPPED

    @pytest.mark.asyncio
    async def test_list_apps_empty(self, mock_httpx_client):
        """Test listing apps with empty response."""
        mock_client, mock_response = mock_httpx_client
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {
                "t": "table",
                "headers": ["NAME", "STATUS", "PORT"],
                "rows": [],
            },
            "id": 1,
        }

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_class.return_value.__aexit__ = AsyncMock(return_value=None)

            client = Hop3Client()
            apps = await client.list_apps()
            assert apps == []

    @pytest.mark.asyncio
    async def test_rpc_error_response(self, mock_httpx_client):
        """Test handling RPC error response."""
        mock_client, mock_response = mock_httpx_client
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32600,
                "message": "Invalid request",
            },
            "id": 1,
        }

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_class.return_value.__aexit__ = AsyncMock(return_value=None)

            client = Hop3Client()
            with pytest.raises(Hop3ClientError, match="Invalid request"):
                await client._rpc_call(["invalid"])

    @pytest.mark.asyncio
    async def test_start_app(self, mock_httpx_client):
        """Test starting an app."""
        mock_client, mock_response = mock_httpx_client
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"t": "text", "text": "Started myapp"},
            "id": 1,
        }

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_class.return_value.__aexit__ = AsyncMock(return_value=None)

            client = Hop3Client()
            result = await client.start_app("myapp")
            assert result is True

            # Verify the call was made
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_app(self, mock_httpx_client):
        """Test stopping an app."""
        mock_client, mock_response = mock_httpx_client
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"t": "text", "text": "Stopped myapp"},
            "id": 1,
        }

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_class.return_value.__aexit__ = AsyncMock(return_value=None)

            client = Hop3Client()
            result = await client.stop_app("myapp")
            assert result is True

    @pytest.mark.asyncio
    async def test_get_app_logs(self, mock_httpx_client):
        """Test getting app logs."""
        mock_client, mock_response = mock_httpx_client
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {
                "t": "text",
                "text": "line1\nline2\nline3",
            },
            "id": 1,
        }

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_class.return_value.__aexit__ = AsyncMock(return_value=None)

            client = Hop3Client()
            logs = await client.get_app_logs("myapp", lines=50)
            assert logs == ["line1", "line2", "line3"]

    @pytest.mark.asyncio
    async def test_get_system_status(self, mock_httpx_client):
        """Test getting system status."""
        mock_client, mock_response = mock_httpx_client
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {},
            "id": 1,
        }

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_class.return_value.__aexit__ = AsyncMock(return_value=None)

            client = Hop3Client()
            status = await client.get_system_status()
            # Returns default SystemStatus since parsing isn't implemented
            assert status.cpu_percent == 0.0
