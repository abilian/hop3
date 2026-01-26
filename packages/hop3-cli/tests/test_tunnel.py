# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import os
import pwd
import socket
import sys
from pathlib import Path

import pytest
from hop3_cli.rpc.tunnel import SSHTunnel
from sshtunnel import SSHTunnelForwarder

# Assuming there is a local SSH server running for testing purposes
TUNNEL_TEST_HOST = "localhost"
TUNNEL_TEST_PORT = 22


def get_current_user():
    """Get the current user name."""
    user_id = os.geteuid()
    return pwd.getpwuid(user_id).pw_name


def ssh_server_available() -> bool:
    """Check if an SSH server is running on localhost:22."""
    try:
        with socket.create_connection((TUNNEL_TEST_HOST, TUNNEL_TEST_PORT), timeout=1):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def ssh_keys_available() -> bool:
    """Check if SSH keys exist for the current user."""
    ssh_dir = Path.home() / ".ssh"
    key_files = ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"]
    return any((ssh_dir / key).exists() for key in key_files)


# Common skip conditions for tunnel tests
requires_ssh_server = pytest.mark.skipif(
    not ssh_server_available(),
    reason="No SSH server running on localhost:22",
)
requires_ssh_keys = pytest.mark.skipif(
    not ssh_keys_available(),
    reason="No SSH keys found in ~/.ssh/",
)
requires_unix = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Test requires Unix-specific modules (pwd, os.geteuid)",
)


@requires_unix
@requires_ssh_server
@requires_ssh_keys
@pytest.mark.skip
def test_custom_tunnel():
    """Test the custom SSHTunnel implementation (currently not used in production)."""

    with SSHTunnel(
        remote_host="localhost",
        remote_port=TUNNEL_TEST_PORT,
        ssh_host=TUNNEL_TEST_HOST,
        ssh_user=get_current_user(),
    ) as tunnel:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", tunnel.local_port))
        s.close()


@requires_unix
@requires_ssh_server
@requires_ssh_keys
@pytest.mark.skip
def test_sshtunnel():
    """Test the sshtunnel package (used in production for SSH tunneling)."""
    server = SSHTunnelForwarder(
        "localhost",
        ssh_username=get_current_user(),
        remote_bind_address=(TUNNEL_TEST_HOST, TUNNEL_TEST_PORT),
    )
    with server:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", server.local_bind_port))
        s.close()
