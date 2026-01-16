# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for deployment target infrastructure."""

from __future__ import annotations

from hop3_testing.targets.base import (
    CommandResult,
    DeployResult,
    HttpResponse,
    TargetCapabilities,
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


class TestTargetCapabilities:
    """Tests for TargetCapabilities dataclass."""

    def test_default_capabilities(self):
        """Test default capability values."""
        caps = TargetCapabilities()

        assert caps.os == "unknown"
        assert caps.arch == "amd64"
        assert caps.has_systemd is False
        assert caps.has_docker is False
        assert caps.available_services == []
        assert caps.network_mode == "isolated"
        assert caps.dns_mode == "none"

    def test_custom_capabilities(self):
        """Test custom capability values."""
        caps = TargetCapabilities(
            os="debian-12",
            arch="arm64",
            has_systemd=True,
            has_docker=True,
            available_services=["postgresql", "redis"],
            network_mode="internet",
            dns_mode="wildcard",
        )

        assert caps.os == "debian-12"
        assert caps.arch == "arm64"
        assert caps.has_systemd is True
        assert caps.has_docker is True
        assert caps.available_services == ["postgresql", "redis"]
        assert caps.network_mode == "internet"
        assert caps.dns_mode == "wildcard"


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
        caps = TargetCapabilities(os="ubuntu-24.04", has_systemd=True)

        info = TargetInfo(
            ssh_host="hop3@server.example.com",
            ssh_port=22,
            ssh_key="/path/to/key",
            http_base="http://server.example.com",
            api_url="http://server.example.com:8000",
            metadata={"container_id": "abc123"},
            capabilities=caps,
        )

        assert info.ssh_host == "hop3@server.example.com"
        assert info.ssh_key == "/path/to/key"
        assert info.http_base == "http://server.example.com"
        assert info.api_url == "http://server.example.com:8000"
        assert info.metadata["container_id"] == "abc123"
        assert info.capabilities.os == "ubuntu-24.04"
        assert info.capabilities.has_systemd is True
