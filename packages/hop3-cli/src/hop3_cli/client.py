# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests
from jsonrpcclient import Error, Ok, parse, request
from jsonrpcclient.responses import Response
from loguru import logger
from sshtunnel import SSHTunnelForwarder

from .exceptions import CliError

if TYPE_CHECKING:
    from .config import Config
    from .state import State


@dataclass
class Client:
    """Hop3 RPC client with reliable SSH tunnel cleanup.

    This class is designed to be used as a context manager to ensure proper
    cleanup of SSH tunnels:

        with Client(config, state) as client:
            result = client.rpc("command", ["arg1", "arg2"])

    When used as a context manager, the SSH tunnel is guaranteed to be stopped
    when exiting the context, even if an exception occurs.
    """

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

    def __enter__(self):
        """Enter context manager - tunnel already started in __post_init__."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - stop tunnel."""
        self.stop()
        return False  # Don't suppress exceptions

    def stop(self):
        """Stop the SSH tunnel if running."""
        if self.tunnel:
            try:
                self.tunnel.stop()
            except Exception as e:
                logger.warning(f"Error stopping SSH tunnel: {e}")
            finally:
                self.tunnel = None

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
        api_url = self.config.get("api_url", "http://localhost:8000")
        assert isinstance(api_url, str)
        return api_url

    @property
    def using_ssh_tunnel(self) -> bool:
        """Check if we're using an SSH tunnel for connection."""
        return self.tunnel is not None

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
        ssh_port = parsed_url.port or self.config.get("ssh_port", 22)

        # The remote port is the one the server is listening on *on the remote machine*.
        remote_server_port = self.config.get("server_port", 8000)

        # Build tunnel kwargs
        tunnel_kwargs = {
            "ssh_username": ssh_user,
            "ssh_port": ssh_port,
            "remote_bind_address": ("localhost", remote_server_port),
        }

        # Add SSH key if provided (optional - can use ssh-agent or default keys)
        ssh_key = self.config.get("ssh_key", None)
        if ssh_key:
            tunnel_kwargs["ssh_pkey"] = ssh_key

        self.tunnel = SSHTunnelForwarder(
            ssh_host,
            **tunnel_kwargs,
        )
        logger.debug(
            f"Starting SSH tunnel to {ssh_host}:{ssh_port} (remote port: {remote_server_port})"
        )
        try:
            self.tunnel.start()
        except Exception as e:
            msg = f"Failed to start SSH tunnel: {e}"
            raise CliError(msg) from e

    def __del__(self):
        """Fallback cleanup (but don't rely on this)."""
        if self.tunnel and getattr(self.tunnel, "is_alive", lambda: False)():
            warnings.warn(
                "SSH tunnel was not properly closed. "
                "Use Client as context manager: `with Client(...) as client:`",
                ResourceWarning,
                stacklevel=2,
            )
            self.stop()

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

        # Build headers with authentication
        headers = {"Content-Type": "application/json"}

        # Add authentication token if configured
        # Note: Even with SSH tunnel, we still use token for authorization
        # SSH provides transport security, token provides authorization
        api_token = self.config.get("api_token", "")
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        response = requests.post(
            self.rpc_url,
            json=json_request,
            headers=headers,
            verify=verify_ssl,  # Use True for HTTPS, False otherwise.
        )
        try:
            # Check for 401 Unauthorized specifically
            if response.status_code == 401:
                error_msg = (
                    "Authentication required.\n\n"
                    "To authenticate, use one of the following methods:\n"
                    "  1. Login: hop auth:login <username> <password>\n"
                    "  2. Register: hop auth:register <username> <email> <password>\n\n"
                    "After logging in, save the token to ~/.config/hop3-cli/config.toml\n"
                    "or set the HOP3_API_TOKEN environment variable."
                )
                return Error(401, error_msg, "", json_request["id"])

            response.raise_for_status()
            parsed_response = parse(response.json())
            # parse() can return Error, Ok, or Iterable[Error | Ok], but we expect single response
            if isinstance(parsed_response, (Error, Ok)):
                return parsed_response
            # Handle batch responses - take first response
            responses = list(parsed_response)
            if responses and isinstance(responses[0], (Error, Ok)):
                return responses[0]
            return Error(-1, "Invalid response format", "", json_request["id"])
        except requests.exceptions.HTTPError as e:
            # For other HTTP errors, provide the status code and message
            # Try to extract error details from response body
            error_detail = f"HTTP {response.status_code} error: {e!s}"
            try:
                error_body = response.json()
                if "detail" in error_body:
                    error_detail += f"\nDetail: {error_body['detail']}"
                elif "error" in error_body:
                    error_detail += f"\nError: {error_body['error']}"
                else:
                    error_detail += f"\nResponse: {error_body}"
            except Exception:
                # If we can't parse JSON, try to show raw response
                if response.text:
                    error_detail += f"\nResponse: {response.text[:500]}"

            return Error(
                response.status_code,
                error_detail,
                "",
                json_request["id"],
            )
        except Exception as e:
            return Error(response.status_code, str(e), "", json_request["id"])
