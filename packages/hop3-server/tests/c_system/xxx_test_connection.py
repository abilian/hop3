# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for SSH connection and CLI availability for remote server diagnostics."""

from __future__ import annotations

import os
import subprocess

import pytest

E2E_SERVER = os.environ.get("HOP3_DEV_HOST", "")

# These tests are for remote server diagnostics only
remote_server_only = pytest.mark.skipif(
    not E2E_SERVER,
    reason="Test is for remote server diagnostics. Set HOP3_DEV_HOST to run.",
)


@remote_server_only
def test_ssh_connection():
    """Test basic SSH connectivity."""
    # Extract user@host from server
    user_host = E2E_SERVER if "@" in E2E_SERVER else f"root@{E2E_SERVER}"

    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", user_host, "echo", "Connection successful"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, f"SSH connection failed: {result.stderr}"


def test_hop3_cli_available():
    """Test if hop3-cli is installed."""
    result = subprocess.run(
        ["which", "hop3"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0, (
        "hop3 command not found in PATH. Install with: pip install -e packages/hop3-cli"
    )
    assert result.stdout.strip(), "hop3 command returned empty output"


@remote_server_only
def test_hop3_cli_connection():
    """Test hop3-cli connection to server."""
    os.environ["HOP3_API_URL"] = f"ssh://{E2E_SERVER}"

    result = subprocess.run(
        ["hop3", "help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"hop3-cli connection failed: {result.stderr}"


@remote_server_only
def test_auth_commands_available():
    """Test if authentication commands are available on the server."""
    os.environ["HOP3_API_URL"] = f"ssh://{E2E_SERVER}"

    result = subprocess.run(
        ["hop3", "help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    # This is informational - don't fail if auth not available
    if not (
        "auth:" in result.stdout
        or "auth:register" in result.stdout
        or "auth:login" in result.stdout
    ):
        pytest.skip("Authentication commands not available on server")


@remote_server_only
def test_auth_register_command():
    """Test if auth:register command works."""
    os.environ["HOP3_API_URL"] = f"ssh://{E2E_SERVER}"

    result = subprocess.run(
        [
            "hop3",
            "auth:register",
            "test-diagnostic-user",
            "test@example.com",
            "test-pass-12345",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    combined_output = result.stdout + result.stderr

    # Authentication not enabled is OK - skip the test
    if "Authentication not enabled" in combined_output:
        pytest.skip("Authentication not enabled on server")

    # User already exists is OK
    assert result.returncode == 0 or "already exists" in combined_output, (
        f"auth:register failed: {result.stderr}\n{result.stdout}"
    )


@remote_server_only
def test_auth_login_command():
    """Test if auth:login command works."""
    os.environ["HOP3_API_URL"] = f"ssh://{E2E_SERVER}"

    result = subprocess.run(
        ["hop3", "auth:login", "test-diagnostic-user", "test-pass-12345"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    combined_output = result.stdout + result.stderr

    # Skip if server isn't properly configured
    if "HOP3_SECRET_KEY must be set" in combined_output:
        pytest.skip("Remote server is not configured with HOP3_SECRET_KEY")

    # Authentication not enabled is OK - skip the test
    if "Authentication not enabled" in combined_output:
        pytest.skip("Authentication not enabled on server")

    assert result.returncode == 0, (
        f"auth:login failed (exit code {result.returncode}):\n"
        f"stdout: {result.stdout[:200]}\n"
        f"stderr: {result.stderr[:200]}"
    )
    # Check for either the old format (raw token) or new format (saved token)
    assert (
        "Your API token:" in result.stdout
        or "API token saved to" in result.stdout
        or "Login successful" in result.stdout
    ), f"auth:login did not show success:\nstdout: {result.stdout[:200]}"
