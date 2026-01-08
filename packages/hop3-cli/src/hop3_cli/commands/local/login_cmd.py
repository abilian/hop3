# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Login command - authenticate to a Hop3 server."""

from __future__ import annotations

import getpass
import os
import sys
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from jsonrpcclient import Error, Ok

from hop3_cli.tokens import extract_jwt

from .help_text import print_login_help
from .ssh_ops import (
    BootstrapError,
    fetch_and_save_certificate,
    get_token_via_ssh,
    infer_server_url,
)

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_login(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the login command.

    Supports multiple authentication methods:
    - URL with token: http://server:port?token=eyJ... (easiest for local dev)
    - --ssh user@server: SSH-based authentication (for remote servers)
    - --token <token>: Use a pre-generated token with separate --server
    - (default): Username/password authentication via the server API

    Usage:
        hop3 login "http://localhost:8000?token=eyJ..."  # URL with embedded token
        hop3 login --ssh user@server                     # SSH-based auth
        hop3 login --token <token> --server <url>        # Separate token and server
        hop3 login                                       # Username/password auth
    """
    # Check for help first
    if "--help" in args or "-h" in args:
        print_login_help()
        return True

    # Check for URL with embedded token (e.g., http://localhost:8000?token=eyJ...)
    if args and not args[0].startswith("-"):
        potential_url = args[0]
        if "?" in potential_url and "token=" in potential_url:
            parsed = urlparse(potential_url)
            query_params = parse_qs(parsed.query)
            if "token" in query_params:
                token = query_params["token"][0]
                # Reconstruct server URL without the token parameter
                server_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                return handle_login_token(
                    ["--token", token, "--server", server_url], config, printer
                )

    # Dispatch based on authentication method
    if "--ssh" in args:
        return handle_login_ssh(args, config, printer)

    if "--token" in args:
        return handle_login_token(args, config, printer)

    # Default: password-based authentication
    return handle_login_password(args, config, printer)


def handle_login_password(
    args: list[str], config: Config, printer: RichPrinter
) -> bool:
    """Handle password-based login via the server API.

    Usage:
        hop3 login
        hop3 login --username admin
    """
    _ensure_server_configured(config)
    username = _parse_username_arg(args)
    username, password = _prompt_credentials(username)

    # Call auth:login via RPC
    print(f"\nAuthenticating as {username}...")

    # Import here to avoid circular import
    from hop3_cli.rpc import Client  # noqa: PLC0415

    with Client(config=config) as client:
        try:
            response = client.rpc("cli", ["auth:login", username, password])
            _handle_login_response(response, username, config, printer)

        except Exception as e:
            print(f"Error during login: {e}", file=sys.stderr)
            sys.exit(1)

    return True


def _ensure_server_configured(config: Config) -> None:
    """Check if server is configured, exit with help if not."""
    if config.is_configured():
        return

    print("Server not configured.", file=sys.stderr)
    print("\nTo configure, use one of:", file=sys.stderr)
    print(
        "  hop3 init --ssh root@your-server.com  # First-time setup",
        file=sys.stderr,
    )
    print(
        "  hop3 login --ssh root@your-server.com # If you have SSH access",
        file=sys.stderr,
    )
    print("  hop3 settings set server https://your-server.com", file=sys.stderr)
    sys.exit(1)


def _parse_username_arg(args: list[str]) -> str | None:
    """Parse --username argument from args."""
    i = 0
    while i < len(args):
        if args[i] == "--username" and i + 1 < len(args):
            return args[i + 1]
        i += 1
    return None


def _prompt_credentials(username: str | None) -> tuple[str, str]:
    """Prompt for username and password, return both."""
    if not username:
        username = input("Username: ").strip()
        if not username:
            print("Error: Username cannot be empty", file=sys.stderr)
            sys.exit(1)

    password = getpass.getpass("Password: ")
    if not password:
        print("Error: Password cannot be empty", file=sys.stderr)
        sys.exit(1)

    return username, password


def _handle_login_response(
    response, username: str, config: Config, printer: RichPrinter
) -> None:
    """Handle the RPC response from auth:login."""
    match response:
        case Ok(result=result):
            token = _extract_token_from_login_response(result)
            if token:
                config.save({"api_token": token})
                print(f"Logged in as {username}")
                print(f"Token saved to {config.config_file}")
            else:
                printer.print(result)
        case Error(message=message):
            print(f"Login failed: {message}", file=sys.stderr)
            sys.exit(1)
        case _:
            print("Unexpected response from server", file=sys.stderr)
            sys.exit(1)


def _extract_token_from_login_response(result: list[dict]) -> str | None:
    """Extract JWT token from auth:login response.

    Args:
        result: The RPC response from auth:login

    Returns:
        The JWT token or None if not found
    """
    for item in result:
        if item.get("t") == "text":
            text = item.get("text", "")
            token = extract_jwt(text)
            if token:
                return token
    return None


def handle_login_token(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle token-based login for local development or automation.

    Usage:
        hop3 login --token <token> --server http://localhost:8000
        hop3 login --token <token>  # Uses existing server config
    """
    token, server_url = _parse_token_args(args)
    server_url = _resolve_server_url(server_url, config)

    # Verify connection before saving
    username = _verify_token(server_url, token)
    if not username:
        sys.exit(1)

    # Save configuration only after successful verification
    config.save({"api_url": server_url, "api_token": token})

    print(f"\nLogged in as {username}")
    print(f"Configuration saved to {config.config_file}")

    return True


def _parse_token_args(args: list[str]) -> tuple[str, str | None]:
    """Parse --token and --server arguments."""
    token = None
    server_url = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--token" and i + 1 < len(args):
            token = args[i + 1]
            i += 2
        elif arg == "--server" and i + 1 < len(args):
            server_url = args[i + 1]
            i += 2
        else:
            i += 1

    if not token:
        print_login_help()
        print("\nError: --token requires a token value", file=sys.stderr)
        sys.exit(1)

    # Type narrowing: token is str after the check above
    assert token is not None

    if not token.startswith("eyJ"):
        print("Warning: Token doesn't look like a JWT token", file=sys.stderr)

    return token, server_url


def _resolve_server_url(server_url: str | None, config) -> str:
    """Resolve server URL from argument, config, or prompt."""
    if server_url:
        return server_url

    existing_url = config.get("api_url", None)
    if existing_url:
        print(f"Using existing server: {existing_url}")
        return existing_url

    # Prompt for URL
    if os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}:
        default_url = "http://localhost:8000"
    else:
        default_url = "https://your-server.com"

    return input(f"Server URL [{default_url}]: ").strip() or default_url


def _verify_token(server_url: str, token: str) -> str | None:
    """Verify token by calling auth:whoami on the server.

    Returns:
        Username if successful, None if verification failed
    """
    # Import here to avoid circular import
    from hop3_cli.config import Config as TempConfig  # noqa: PLC0415
    from hop3_cli.rpc import Client  # noqa: PLC0415

    # Create a temporary config for verification
    temp_config = TempConfig(
        data={"api_url": server_url, "api_token": token},
        config_file=None,
    )

    print(f"Verifying connection to {server_url}...")

    try:
        with Client(config=temp_config) as client:
            response = client.rpc("cli", ["auth:whoami"])

            match response:
                case Ok(result=result):
                    # Extract username from response
                    return _extract_username_from_whoami(result)
                case Error(message=message):
                    print(f"Authentication failed: {message}", file=sys.stderr)
                    return None
                case _:
                    print("Unexpected response from server", file=sys.stderr)
                    return None

    except Exception as e:
        error_str = str(e).lower()
        # Check for connection-related errors
        if "connection refused" in error_str or "failed to establish" in error_str:
            print(f"Could not connect to {server_url}", file=sys.stderr)
            print("Is the server running?", file=sys.stderr)
        elif "timeout" in error_str:
            print(f"Connection to {server_url} timed out.", file=sys.stderr)
            print("The server may be slow or unreachable.", file=sys.stderr)
        elif "ssl" in error_str or "certificate" in error_str:
            print(f"SSL/TLS error connecting to {server_url}", file=sys.stderr)
            print(
                "Check that the server URL is correct (http vs https).", file=sys.stderr
            )
        else:
            print(f"Could not connect to {server_url}", file=sys.stderr)
        return None


def _extract_username_from_whoami(result: list[dict]) -> str | None:
    """Extract username from auth:whoami response."""
    for item in result:
        if item.get("t") == "text":
            text = item.get("text", "")
            # Look for "Logged in as: username" or similar patterns
            if "Logged in as:" in text:
                parts = text.split("Logged in as:")
                if len(parts) > 1:
                    return parts[1].strip().split()[0]
            # Fallback: return first non-empty word
            words = text.strip().split()
            if words:
                return words[0]
    return "user"  # Default if we can't extract


def handle_login_ssh(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the login --ssh command for getting token via SSH.

    Usage:
        hop3 login --ssh user@server
        hop3 login --ssh user@server --username admin
    """
    ssh_target, username, server_url = _parse_login_ssh_args(args)

    # Prompt for username if not provided
    if not username:
        username = input("Username: ").strip()
        if not username:
            print("Error: Username cannot be empty", file=sys.stderr)
            sys.exit(1)

    # Execute via SSH
    print(f"\nConnecting to {ssh_target}...")

    try:
        token = get_token_via_ssh(ssh_target, username)
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Prepare and save config
    config_data = {"api_url": server_url, "api_token": token}
    _handle_ssl_certificate(ssh_target, server_url, config, config_data)
    config.save(config_data)

    _print_login_success(username, config)
    return True


def _parse_login_ssh_args(args: list[str]) -> tuple[str, str | None, str]:
    """Parse arguments for login --ssh command.

    Returns:
        Tuple of (ssh_target, username, server_url)
    """
    ssh_target = None
    username = None
    server_url = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--ssh" and i + 1 < len(args):
            ssh_target = args[i + 1]
            i += 2
        elif arg == "--username" and i + 1 < len(args):
            username = args[i + 1]
            i += 2
        elif arg == "--server" and i + 1 < len(args):
            server_url = args[i + 1]
            i += 2
        else:
            i += 1

    if not ssh_target:
        print_login_help()
        print(
            "\nError: --ssh requires a target (e.g., root@server.com)", file=sys.stderr
        )
        sys.exit(1)

    # Type narrowing: ssh_target is str after the check above
    assert ssh_target is not None

    # Infer server URL from SSH target if not provided
    if not server_url:
        server_url = infer_server_url(ssh_target)
        response = input(f"Server URL [{server_url}]: ").strip()
        if response:
            server_url = response

    return ssh_target, username, server_url


def _handle_ssl_certificate(
    ssh_target: str, server_url: str, config: Config, config_data: dict
) -> None:
    """Handle SSL certificate fetching for HTTPS connections.

    Updates config_data with ssl_cert path if successful.
    """
    existing_cert = config.get("ssl_cert", None)
    existing_verify = config.get("verify_ssl", None)

    if not server_url.startswith("https://"):
        return
    if existing_cert or existing_verify is not None:
        return

    parsed = urlparse(server_url)
    hostname = parsed.hostname

    # Check if connecting via IP address
    is_ip_address = hostname and (
        hostname.replace(".", "").isdigit() or ":" in hostname
    )

    print("\nFetching SSL certificate...")
    try:
        cert_path = fetch_and_save_certificate(ssh_target, server_url, config)
        if cert_path:
            config_data["ssl_cert"] = str(cert_path)
            print(f"  Certificate saved to {cert_path}")
            if is_ip_address:
                print(
                    "  Note: Using IP address - hostname verification will be skipped,"
                )
                print("        but certificate will still be verified.")
    except Exception as e:
        print(f"  Warning: Could not fetch certificate: {e}")
        print("  You may need to configure SSL manually with:")
        print("    hop3 settings set verify_ssl false")


def _print_login_success(username: str, config: Config) -> None:
    """Print success message after login."""
    print(f"\nToken generated for user '{username}'")
    print(f"Configuration saved to {config.config_file}")
    print("\nWelcome back! Try:")
    print("  hop3 apps           # List applications")
    print("  hop3 auth:whoami    # Check current user")
