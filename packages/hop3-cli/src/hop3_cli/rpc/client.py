# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import requests
from jsonrpcclient import Error, Ok, parse, request
from loguru import logger

from hop3_cli.core.ssh_tunnel import SshTunnel
from hop3_cli.exceptions import AuthenticationError, CliError

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Self

    from jsonrpcclient.responses import Response

    from hop3_cli.config import Config

# SECURITY (audit M8): bound the RPC request so a malicious or unresponsive
# server can't hang the CLI forever with the bearer token in transit. Mirrors
# the SSE path's timeouts (streaming.py). (connect, read) seconds.
_RPC_CONNECT_TIMEOUT_SECONDS = 30.0
_RPC_READ_TIMEOUT_SECONDS = 300.0

# audit M2: we do NOT call urllib3.disable_warnings() here. When TLS
# verification is disabled (verify_ssl=false on an https URL), urllib3's
# InsecureRequestWarning is the operator's only signal that traffic —
# including the bearer token — is interceptable. Suppressing it globally hid a
# silent-MITM foot-gun. Left unsuppressed so the warning surfaces.


def resolve_ssl_verification(api_url: str, config: Config) -> bool | str:
    """
    The ``verify`` value for ``requests`` given the connection URL + config.

    Shared by the RPC client AND the SSE streaming path so both honor a pinned
    ``ssl_cert`` (chain-verify against it) and parse a string ``verify_ssl``
    ("false"/"0"/"no") identically. A non-HTTPS URL needs no verification.

    The streaming path used to hand-roll ``config.get("verify_ssl", True)``,
    which ignored a pinned ``ssl_cert`` (so the stream failed while ``/rpc``
    succeeded, reporting failure on a running deploy) and passed a *string*
    ``"false"`` straight to ``requests`` (read as a CA-bundle path → opaque
    OSError). Routing both through this one resolver closes that (audit
    2026-06 B1).
    """
    if urlparse(api_url).scheme != "https":
        return False

    ssl_cert_value = config.get("ssl_cert", None)
    if ssl_cert_value:
        # Pinned cert: verify the chain against it (hostname/SAN included).
        return str(ssl_cert_value)

    return not _verify_ssl_disabled(config.get("verify_ssl", None))


def _verify_ssl_disabled(verify_ssl_config: object) -> bool:
    """Whether ``verify_ssl`` is explicitly disabled (handles str + bool)."""
    if verify_ssl_config is None:
        return False
    if isinstance(verify_ssl_config, str):
        return verify_ssl_config.lower() in {"false", "0", "no"}
    return not bool(verify_ssl_config)


@dataclass
class Client:
    """
    Hop3 RPC client with reliable SSH tunnel cleanup.

    This class is designed to be used as a context manager to ensure proper
    cleanup of SSH tunnels:

        with Client(config) as client:
            result = client.rpc("command", ["arg1", "arg2"])

    When used as a context manager, the SSH tunnel is guaranteed to be stopped
    when exiting the context, even if an exception occurs.
    """

    config: Config
    tunnel: SshTunnel | None = None

    api_url_override: str | None = None

    def __post_init__(self) -> None:
        """Initialize the SSH tunnel only if the scheme is ssh."""
        parsed_url = urlparse(self.api_url)
        if parsed_url.scheme in {"ssh", "ssh+http"}:
            if not self.tunnel:
                self.start_ssh_tunnel()

    def __enter__(self) -> Self:
        """Enter context manager - tunnel already started in __post_init__."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """Exit context manager - stop tunnel."""
        self.stop()
        return False  # Don't suppress exceptions

    def stop(self) -> None:
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

    def start_ssh_tunnel(self) -> None:
        """Starts the SSH tunnel based on the parsed api_url."""
        parsed_url = urlparse(self.api_url)

        ssh_host = parsed_url.hostname
        if not ssh_host:
            msg = f"SSH server URL has no hostname: {self.api_url!r}"
            raise CliError(msg)
        ssh_user = parsed_url.username or self.config.get("ssh_user", "root")
        ssh_port = parsed_url.port or self.config.get("ssh_port", 22)
        # The remote port is the one hop3-server listens on *on the remote box*.
        remote_server_port = self.config.get("server_port", 8000)
        # Optional key; when absent, ssh uses ~/.ssh/config / agent / default keys.
        ssh_key_value = self.config.get("ssh_key", None)
        ssh_key = ssh_key_value if isinstance(ssh_key_value, str) else None

        self.tunnel = SshTunnel(
            ssh_host,
            remote_server_port,
            user=ssh_user,
            ssh_port=ssh_port,
            key=ssh_key,
        )
        logger.debug(
            f"Starting SSH tunnel to {ssh_host}:{ssh_port} (remote port: {remote_server_port})"
        )
        try:
            self.tunnel.start()
        except Exception as e:
            msg = f"Failed to start SSH tunnel: {e}"
            raise CliError(msg) from e

    def __del__(self) -> None:
        """Fallback cleanup (but don't rely on this)."""
        if self.tunnel and getattr(self.tunnel, "is_alive", lambda: False)():
            warnings.warn(
                "SSH tunnel was not properly closed. "
                "Use Client as context manager: `with Client(...) as client:`",
                ResourceWarning,
                stacklevel=2,
            )
            self.stop()

    def rpc(self, method: str, cli_args: list[str], **extra_args: object) -> Response:
        """
        Call a remote method with automatic SSH-based authentication.

        If the request returns 401 and we have SSH access configured,
        automatically authenticate via SSH and retry the request.
        """
        response = self._do_rpc(method, cli_args, **extra_args)

        # If 401 and we can auto-auth via SSH, try it
        if isinstance(response, Error) and response.code == 401:
            if self._can_auto_auth():
                logger.debug("Got 401, attempting auto-auth via SSH")
                try:
                    self._auto_authenticate()
                    logger.debug("Auto-auth successful, retrying request")
                    response = self._do_rpc(method, cli_args, **extra_args)
                except AuthenticationError:
                    logger.debug("Auto-auth failed, returning original 401 response")

        return response

    def _do_rpc(
        self, method: str, cli_args: list[str], **extra_args: object
    ) -> Response:
        """Execute the actual RPC call."""
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
            timeout=(_RPC_CONNECT_TIMEOUT_SECONDS, _RPC_READ_TIMEOUT_SECONDS),
        )

        return self._parse_response(response, json_request)

    def _can_auto_auth(self) -> bool:
        """Check if we can auto-authenticate via SSH."""
        parsed = urlparse(self.api_url)
        return parsed.scheme in {"ssh", "ssh+http"}

    def _auto_authenticate(self) -> None:
        """
        Get a new token via SSH and save it to config.

        Raises:
            AuthenticationError: If authentication fails.
        """
        from hop3_cli.commands.local.ssh_ops import (  # ruff:ignore[import-outside-top-level]
            BootstrapError,
            get_ssh_token,
        )

        parsed = urlparse(self.api_url)
        ssh_user = parsed.username or self.config.get("ssh_user", "root")
        ssh_host = parsed.hostname
        ssh_target = f"{ssh_user}@{ssh_host}"

        logger.debug(f"Auto-authenticating via SSH to {ssh_target}")

        try:
            token = get_ssh_token(ssh_target)
        except BootstrapError as e:
            msg = f"SSH authentication to {ssh_target} failed: {e}"
            raise AuthenticationError(msg) from e

        # Save token to current context (or legacy config)
        self.config.update_context_token(token)

    def _get_ssl_verification(self) -> bool | str:
        """
        Determine SSL verification mode based on config.

        A pinned ``ssl_cert`` is always returned (chain-verified against the
        cert, including hostname/SAN); operators wanting IP-based access must
        include the IP in the cert's SAN. See notes/security.md §3.4 for the
        trust-model rationale. Delegates to the module-level
        ``resolve_ssl_verification`` shared with the streaming path.
        """
        return resolve_ssl_verification(self.api_url, self.config)

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with authentication."""
        headers = {"Content-Type": "application/json"}
        api_token = self.config.get_api_token()
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
            "Log in with the credentials an administrator created for you:\n"
            "  hop3 login\n\n"
            "This saves the token for you. For scripts, mint one explicitly:\n"
            "  hop3 auth get-token <username> --password-file -"
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
