# Copyright (c) 2023-2025, Abilian SAS
"""RPC client for Hop3 server. Uses JSON-RPC over HTTP with SSH tunneling.

Alternatively, it could use HTTPS with proper key exchange and
certificate validation, but this still needs to be implemented.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

import requests
from jsonrpcclient import Error, parse, request
from jsonrpcclient.responses import Response
from loguru import logger
from sshtunnel import SSHTunnelForwarder

from .exceptions import CliError

if TYPE_CHECKING:
    from .config import Config
    from .state import State


# TODO: use State


@dataclass
class Client:
    config: Config
    state: State | None
    tunnel: SSHTunnelForwarder | None = None

    def __post_init__(self):
        """Initialize the SSH tunnel if not already started."""
        if self.host != "localhost" and not self.tunnel:
            self.start_ssh_tunnel()

    @cached_property
    def host(self):
        hop3_server = os.environ.get("HOP3_SERVER", "localhost")
        # Alternatively, we could get the remote from git config:
        # git_remote = run_command("git config --get remote.hop3.url")
        return hop3_server

    @cached_property
    def server_port(self):
        return self.config["server_port"]

    @property
    def local_port(self):
        """Return the local port for the SSH tunnel."""
        assert self.tunnel
        return self.tunnel.local_bind_port

    @property
    def rpc_url(self):
        """Return the RPC URL."""
        if self.tunnel:
            return f"http://localhost:{self.local_port}/rpc"
        else:
            return f"http://localhost:{self.server_port}/rpc"

    def start_ssh_tunnel(self):
        self.tunnel = SSHTunnelForwarder(
            self.host,
            ssh_username="root",
            remote_bind_address=("localhost", self.server_port),
        )
        logger.debug(f"Starting SSH tunnel to {self.host}:{self.server_port}")
        try:
            self.tunnel.start()
        except Exception as e:
            msg = f"Failed to start SSH tunnel: {e}"
            raise CliError(msg) from e

    def __del__(self):
        if self.tunnel:
            self.tunnel.stop()
            self.tunnel = None

    def rpc(self, method: str, *args: list[str]) -> Response:
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
