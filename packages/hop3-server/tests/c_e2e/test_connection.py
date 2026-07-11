# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Remote-server diagnostic tests for SSH connectivity and CLI availability.

These tests poke a REAL remote server, so they are opt-in: they run only when
``--ssh-host HOST`` is passed (the ``remote_server`` fixture skips otherwise).
They deliberately do NOT read HOP3_DEV_HOST / HOP3_TEST_HOST — an ambient env
var must never redirect a pytest run at a real box (ADR 043).
"""

from __future__ import annotations

import subprocess

import pytest


@pytest.fixture
def remote_server(remote_ssh_host: str | None) -> str:
    """The explicit remote target as ``user@host``; skip when not opted in.

    ``remote_ssh_host`` is the root-conftest fixture backed by ``--ssh-host``.
    """
    if not remote_ssh_host:
        pytest.skip(
            "remote diagnostics: pass --ssh-host HOST to run "
            "(HOP3_DEV_HOST / HOP3_TEST_HOST are ignored on purpose)"
        )
    return remote_ssh_host if "@" in remote_ssh_host else f"root@{remote_ssh_host}"


def test_ssh_connection(remote_server: str) -> None:
    """Test basic SSH connectivity."""
    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", remote_server, "echo", "ok"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, f"SSH connection failed: {result.stderr}"


def test_hop3_cli_available() -> None:
    """Test if hop3-cli is installed (local check; always runs)."""
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


def test_hop3_cli_connection(
    remote_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test hop3-cli connection to server."""
    monkeypatch.setenv("HOP3_API_URL", f"ssh://{remote_server}")

    result = subprocess.run(
        ["hop3", "help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"hop3-cli connection failed: {result.stderr}"


def test_auth_commands_available(
    remote_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test if authentication commands are available on the server."""
    monkeypatch.setenv("HOP3_API_URL", f"ssh://{remote_server}")

    result = subprocess.run(
        ["hop3", "help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    # This is informational - don't fail if auth not available
    if not any(
        marker in result.stdout
        for marker in ("auth:", "auth login", "auth get-token", "auth whoami")
    ):
        pytest.skip("Authentication commands not available on server")


def test_auth_register_command(
    remote_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test if auth:register command works."""
    monkeypatch.setenv("HOP3_API_URL", f"ssh://{remote_server}")

    result = subprocess.run(
        [
            "hop3",
            "auth",
            "register",
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


def test_auth_get_token_command(
    remote_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that `auth get-token` verifies credentials and prints a JWT.

    `auth get-token` is the non-interactive primitive behind `hop3 login`: it
    takes a username + password and prints the bare token (for scripts). The
    interactive `auth login` / `hop3 login` flow is client-side and prompts, so
    it can't be exercised non-interactively here.
    """
    monkeypatch.setenv("HOP3_API_URL", f"ssh://{remote_server}")

    result = subprocess.run(
        ["hop3", "auth", "get-token", "test-diagnostic-user", "test-pass-12345"],
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
        f"auth get-token failed (exit code {result.returncode}):\n"
        f"stdout: {result.stdout[:200]}\n"
        f"stderr: {result.stderr[:200]}"
    )
    # Output is the bare JWT (header.payload.signature).
    token = next(
        (
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().count(".") == 2 and line.strip().startswith("ey")
        ),
        None,
    )
    assert token, f"auth get-token did not return a JWT:\nstdout: {result.stdout[:200]}"
