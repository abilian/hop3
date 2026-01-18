# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests
import urllib3
import urllib3.exceptions
from jsonrpcclient import Error, Ok, parse, request
from jsonrpcclient.responses import Response
from loguru import logger

# sshtunnel uses paramiko which has deprecated TripleDES warnings
# TODO: Consider replacing sshtunnel with subprocess-based ssh port forwarding
# to eliminate paramiko dependency entirely. This would use native ssh -L
# which is simpler and avoids Python crypto library deprecation issues.
from sshtunnel import SSHTunnelForwarder

from hop3_cli.exceptions import CliError

if TYPE_CHECKING:
    from hop3_cli.config import Config

# Suppress InsecureRequestWarning when SSL verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _is_ip_address(hostname: str) -> bool:
    """Check if hostname is an IP address."""
    # IPv4 pattern
    ipv4_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    # IPv6 pattern (simplified - brackets or raw)
    ipv6_pattern = r"^\[?[0-9a-fA-F:]+\]?$"
    return bool(re.match(ipv4_pattern, hostname) or re.match(ipv6_pattern, hostname))


@dataclass
class Client:
    """Hop3 RPC client with reliable SSH tunnel cleanup.

    This class is designed to be used as a context manager to ensure proper
    cleanup of SSH tunnels:

        with Client(config) as client:
            result = client.rpc("command", ["arg1", "arg2"])

    When used as a context manager, the SSH tunnel is guaranteed to be stopped
    when exiting the context, even if an exception occurs.
    """

    config: Config
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
        4. Developer mode (HOP3_DEV_MODE=true) enables localhost:8000.
        """
        # The main.py will need to be updated to pass the --api-url flag value here.
        if self.api_url_override:
            return self.api_url_override

        # Use the config's get_api_url which handles dev mode and returns None if unconfigured
        api_url = self.config.get_api_url()
        if api_url is None:
            # This shouldn't happen if main.py checks is_configured() first,
            # but provide a sensible fallback for direct Client usage
            msg = "API URL not configured. Run 'hop3 init --ssh root@server' to set up."
            raise CliError(msg)
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

    def rpc(self, method: str, cli_args: list[str], **extra_args: Any) -> Response:
        """Call a remote method."""
        args = {
            "cli_args": cli_args,
            "extra_args": extra_args,
        }
        json_request = request(method, args)

        verify_ssl = self._get_ssl_verification()
        headers = self._build_headers()

        response = requests.post(
            self.rpc_url,
            json=json_request,
            headers=headers,
            verify=verify_ssl,
        )

        return self._parse_response(response, json_request)

    def _get_ssl_verification(self) -> bool | str:
        """Determine SSL verification mode based on config."""
        parsed_url = urlparse(self.api_url)

        if parsed_url.scheme != "https":
            return False

        ssl_cert = self.config.get("ssl_cert", None)
        verify_ssl_config = self.config.get("verify_ssl", None)
        hostname = parsed_url.hostname or ""

        # Check if verification is explicitly disabled
        verify_ssl_disabled = self._is_verify_ssl_disabled(verify_ssl_config)

        if ssl_cert and _is_ip_address(hostname):
            # IP address with saved cert: skip verification
            # (cert was fetched via trusted SSH, hostname check would fail)
            return False
        if ssl_cert:
            # Hostname with saved cert: standard verification with custom CA
            return ssl_cert

        # Default to system CA bundle unless explicitly disabled
        return not verify_ssl_disabled

    def _is_verify_ssl_disabled(
        self,
        verify_ssl_config: str | bool | None,  # noqa: FBT001
    ) -> bool:
        """Check if SSL verification is explicitly disabled in config."""
        if verify_ssl_config is None:
            return False
        if isinstance(verify_ssl_config, str):
            return verify_ssl_config.lower() in {"false", "0", "no"}
        return not bool(verify_ssl_config)

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with authentication."""
        headers = {"Content-Type": "application/json"}
        api_token = self.config.get("api_token", "")
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        return headers

    def _parse_response(
        self, response: requests.Response, json_request: dict
    ) -> Response:
        """Parse HTTP response into JSON-RPC response."""
        request_id = json_request["id"]

        try:
            if response.status_code == 401:
                return self._make_auth_error(request_id)

            # Try to parse as JSON-RPC response (even for non-200 status codes)
            json_rpc_response = self._try_parse_jsonrpc(response, request_id)
            if json_rpc_response is not None:
                return json_rpc_response

            # For non-200 responses without JSON-RPC error, raise HTTP error
            response.raise_for_status()
            return Error(-1, "Unexpected response format", "", request_id)

        except requests.exceptions.HTTPError as e:
            error_detail = f"HTTP {response.status_code} error: {e!s}"
            if response.text:
                error_detail += f"\nResponse: {response.text[:500]}"
            return Error(response.status_code, error_detail, "", request_id)
        except Exception as e:
            return Error(response.status_code, str(e), "", request_id)

    def _make_auth_error(self, request_id: int) -> Error:
        """Create authentication required error."""
        error_msg = (
            "Authentication required.\n\n"
            "To authenticate, use one of the following methods:\n"
            "  1. Login: hop auth:login <username> <password>\n"
            "  2. Register: hop auth:register <username> <email> <password>\n\n"
            "After logging in, save the token to ~/.config/hop3-cli/config.toml\n"
            "or set the HOP3_API_TOKEN environment variable."
        )
        return Error(401, error_msg, "", request_id)

    def _try_parse_jsonrpc(
        self, response: requests.Response, request_id: int
    ) -> Response | None:
        """Try to parse response as JSON-RPC. Returns None if not valid JSON-RPC."""
        try:
            json_body = response.json()
        except ValueError:
            return None

        # Check if this is a JSON-RPC error response
        if "error" in json_body and isinstance(json_body["error"], dict):
            rpc_error = json_body["error"]
            return Error(
                rpc_error.get("code", response.status_code),
                rpc_error.get("message", "Unknown error"),
                rpc_error.get("data", ""),
                request_id,
            )

        # Parse successful JSON-RPC response
        if response.ok:
            parsed_response = parse(json_body)
            if isinstance(parsed_response, (Error, Ok)):
                return parsed_response
            # Handle batch responses - take first response
            responses = list(parsed_response)
            if responses and isinstance(responses[0], (Error, Ok)):
                return responses[0]
            return Error(-1, "Invalid response format", "", request_id)

        return None
