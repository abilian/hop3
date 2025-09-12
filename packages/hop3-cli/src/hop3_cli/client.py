# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests
from jsonrpcclient import Error, parse, request
from jsonrpcclient.responses import Response
from loguru import logger
from sshtunnel import SSHTunnelForwarder

from .exceptions import CliError

if TYPE_CHECKING:
    from .config import Config
    from .state import State


@dataclass
class Client:
    config: Config
    state: State | None
    tunnel: SSHTunnelForwarder | None = None

    api_url_override: str | None = None

    def __post_init__(self):
        """Initialize the SSH tunnel only if the scheme is ssh."""
        parsed_url = urlparse(self.api_url)
        if parsed_url.scheme in {"ssh", "ssh+http"}:
            if not self.tunnel:
                self.start_ssh_tunnel()

    @cached_property
    def api_url(self) -> str:
        """
        Determine the API URL to use.
        Priority:
        1. Explicit override passed to the Client.
        2. HOP3_API_URL environment variable.
        3. URL from config file.
        """
        # The main.py will need to be updated to pass the --api-url flag value here.
        if self.api_url_override:
            return self.api_url_override

        # This uses the config's layered approach (env > file > default)
        return self.config.get("api_url", "http://localhost:8000")

    @property
    def rpc_url(self) -> str:
        """Return the correct RPC URL based on the connection type."""
        parsed_url = urlparse(self.api_url)

        if self.tunnel:
            # If tunneled, the RPC endpoint is always on localhost at the tunnel's local port.
            return f"http://localhost:{self.tunnel.local_bind_port}/rpc"

        # For direct http/https, use the api_url directly.
        if parsed_url.scheme in {"http", "https"}:
            return f"{self.api_url.rstrip('/')}/rpc"

        msg = f"Unsupported scheme in API URL: {parsed_url.scheme}"
        raise CliError(msg)

    def start_ssh_tunnel(self):
        """Starts the SSH tunnel based on the parsed api_url."""
        parsed_url = urlparse(self.api_url)

        ssh_host = parsed_url.hostname
        ssh_user = parsed_url.username or self.config.get("ssh_user", "root")

        # The remote port is the one the server is listening on *on the remote machine*.
        remote_server_port = self.config.get("server_port", 8000)

        self.tunnel = SSHTunnelForwarder(
            ssh_host,
            ssh_username=ssh_user,
            remote_bind_address=("localhost", remote_server_port),
        )
        logger.debug(
            f"Starting SSH tunnel to {ssh_host} (remote port: {remote_server_port})"
        )
        try:
            self.tunnel.start()
        except Exception as e:
            msg = f"Failed to start SSH tunnel: {e}"
            raise CliError(msg) from e

    def __del__(self):
        if self.tunnel:
            self.tunnel.stop()
            self.tunnel = None

    def rpc(
        self, method: str, cli_args: list[str], **extra_args: dict[str, Any]
    ) -> Response:
        """Call a remote method."""
        args = {
            "cli_args": cli_args,
            "extra_args": extra_args,
        }
        json_request = request(method, args)

        # Determine if we should verify SSL certs
        verify_ssl = urlparse(self.api_url).scheme == "https"

        response = requests.post(
            self.rpc_url,
            json=json_request,
            verify=verify_ssl,  # Use True for HTTPS, False otherwise.
        )
        try:
            response.raise_for_status()
            return parse(response.json())
        except Exception as e:
            return Error(response.status_code, str(e), "", json_request["id"])
