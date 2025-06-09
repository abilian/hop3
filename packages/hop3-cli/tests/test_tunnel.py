# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import os
import pwd
import socket

from hop3_cli.tunnel import SSHTunnel
from sshtunnel import SSHTunnelForwarder

# Asuming there is a local SSH server running for testing purposes
TUNNEL_TEST_HOST = "localhost"
TUNNEL_TEST_PORT = 22
TUNNEL_TEST_USER = ""


def get_current_user():
    """Get the current user name."""
    user_id = os.geteuid()
    return pwd.getpwuid(user_id).pw_name


def test_custom_tunnel():
    with SSHTunnel(
        remote_host="localhost",
        remote_port=TUNNEL_TEST_PORT,
        ssh_host=TUNNEL_TEST_HOST,
        ssh_user=get_current_user(),
    ) as tunnel:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", tunnel.local_port))


def test_sshtunnel():
    server = SSHTunnelForwarder(
        "localhost",
        ssh_username=get_current_user(),
        remote_bind_address=(TUNNEL_TEST_HOST, TUNNEL_TEST_PORT),
    )
    with server:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", server.local_bind_port))
