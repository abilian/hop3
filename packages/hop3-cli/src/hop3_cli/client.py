# Copyright (c) 2023-2025, Abilian SAS
"""RPC client for Hop3 server. Uses JSON-RPC over HTTP with SSH tunneling.

Alternatively, it could use HTTPS with proper key exchange and
certificate validation, but this still needs to be implemented.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests
from jsonrpcclient import Error, parse, request
from sshtunnel import SSHTunnelForwarder

if TYPE_CHECKING:
    from .config import Config
    from .state import State


# TODO: use State


@dataclass
class Client:
    config: Config
    state: State | None
    tunnel: SSHTunnelForwarder | None = None

    @property
    def host(self):
        hop3_server = os.environ("HOP3_SERVER")
        # Alternatively, we could get the remote from git config:
        # git_remote = run_command("git config --get remote.hop3.url")
        if not hop3_server:
            msg = "HOP3_SERVER environment variable is not set"
            raise ValueError(msg)
        return hop3_server

    @property
    def port(self):
        return self.config.get("port", 8000)

    @property
    def local_port(self):
        """Return the local port for the SSH tunnel."""
        assert self.tunnel
        return self.tunnel.local_bind_port

    @property
    def rpc_url(self):
        """Return the RPC URL."""
        return f"http://localhost:{self.local_port}/rpc"

    def start_ssh_tunnel(
        self,
    ):
        self.tunnel = SSHTunnelForwarder(
            "localhost",
            ssh_username="hop3",
            remote_bind_address=(self.host, self.port),
        )
        self.tunnel.start()

    def __del__(self):
        if self.tunnel:
            self.tunnel.stop()
            self.tunnel = None

    def rpc(self, method: str, *args: list[str]) -> Error | dict:
        """Call a remote method."""
        json_request = request(method, args)
        response = requests.post(
            self.rpc_url,
            json=json_request,
            # verify=False,
            # cert="../hop3-server/ssl/cert.pem",
        )
        try:
            response.raise_for_status()
            return parse(response.json())
        except Exception as e:
            return Error(response.status_code, str(e), "", json_request["id"])
