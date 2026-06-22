# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for deployment target infrastructure."""

from __future__ import annotations

from hop3_testing.targets.base import (
    CommandResult,
    DeployResult,
    HttpResponse,
    TargetInfo,
)


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_result(self):
        """Test creating a successful command result."""
        result = CommandResult(
            success=True,
            stdout="output",
            stderr="",
            returncode=0,
            duration=1.5,
        )

        assert result.success is True
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.returncode == 0
        assert result.duration == 1.5

    def test_failure_result(self):
        """Test creating a failed command result."""
        result = CommandResult(
            success=False,
            stdout="",
            stderr="error message",
            returncode=1,
        )

        assert result.success is False
        assert result.stderr == "error message"
        assert result.returncode == 1
        assert result.duration == 0.0  # default value


class TestDeployResult:
    """Tests for DeployResult dataclass."""

    def test_successful_deploy(self):
        """Test creating a successful deploy result."""
        result = DeployResult(
            success=True,
            app_name="my-app",
            app_url="http://my-app.example.com",
            logs="Deployed successfully",
            duration=30.5,
        )

        assert result.success is True
        assert result.app_name == "my-app"
        assert result.app_url == "http://my-app.example.com"
        assert result.logs == "Deployed successfully"
        assert result.duration == 30.5
        assert result.error is None

    def test_failed_deploy(self):
        """Test creating a failed deploy result."""
        result = DeployResult(
            success=False,
            app_name="broken-app",
            error="Build failed",
            duration=5.0,
        )

        assert result.success is False
        assert result.app_name == "broken-app"
        assert result.app_url is None
        assert result.error == "Build failed"


class TestHttpResponse:
    """Tests for HttpResponse dataclass."""

    def test_successful_response(self):
        """Test creating a successful HTTP response."""
        response = HttpResponse(
            status=200,
            body='{"message": "ok"}',
            headers={"Content-Type": "application/json"},
            duration=0.1,
        )

        assert response.status == 200
        assert response.body == '{"message": "ok"}'
        assert response.headers["Content-Type"] == "application/json"
        assert response.duration == 0.1

    def test_error_response(self):
        """Test creating an error HTTP response."""
        response = HttpResponse(
            status=500,
            body="Internal Server Error",
        )

        assert response.status == 500
        assert response.body == "Internal Server Error"
        assert response.headers == {}  # default empty dict
        assert response.duration == 0.0  # default value


class TestTargetInfo:
    """Tests for TargetInfo dataclass."""

    def test_minimal_target_info(self):
        """Test creating minimal target info."""
        info = TargetInfo(
            ssh_host="hop3@192.168.1.100",
            ssh_port=22,
        )

        assert info.ssh_host == "hop3@192.168.1.100"
        assert info.ssh_port == 22
        assert info.ssh_key is None
        assert info.ssh_password is None
        assert info.http_base == ""
        assert info.api_url == ""

    def test_full_target_info(self):
        """Test creating full target info."""
        info = TargetInfo(
            ssh_host="hop3@server.example.com",
            ssh_port=22,
            ssh_key="/path/to/key",
            http_base="http://server.example.com",
            api_url="http://server.example.com:8000",
            metadata={"container_id": "abc123"},
        )

        assert info.ssh_host == "hop3@server.example.com"
        assert info.ssh_key == "/path/to/key"
        assert info.http_base == "http://server.example.com"
        assert info.api_url == "http://server.example.com:8000"
        metadata = info.metadata
        assert metadata is not None
        assert metadata["container_id"] == "abc123"
