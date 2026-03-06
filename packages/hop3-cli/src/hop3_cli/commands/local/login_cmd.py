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
    get_magic_link_via_ssh,
    get_ssh_token,
    get_token_via_ssh,
    infer_server_url,
)

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_login(args: list[str], config: Config, printer: RichPrinter) -> None:
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
        return

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
                handle_login_token(
                    ["--token", token, "--server", server_url], config, printer
                )
                return

    # Dispatch based on authentication method
    if "--web" in args:
        handle_login_web(args, config, printer)
    elif "--ssh" in args:
        handle_login_ssh(args, config, printer)
    elif "--token" in args:
        handle_login_token(args, config, printer)
    else:
        # Default: password-based authentication
        handle_login_password(args, config, printer)


def handle_login_password(
    args: list[str], config: Config, printer: RichPrinter
) -> None:
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
                context_name = config.get_current_context_name()
                if context_name:
                    config.update_context_token(token)
                else:
                    # No context exists - must have one to do password login
                    print(
                        "Error: No context configured. Use 'hop3 init' or 'hop3 login --ssh' first.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                print(f"Logged in as {username}")
                print(f"Token saved to context '{context_name}'")
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


def handle_login_web(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Handle --web flag to generate a magic link for browser login.

    This generates a short-lived, single-use URL that can be used to log into
    the web dashboard without entering a password. Requires SSH access.

    Usage:
        hop3 login --web user@server
        hop3 login --web user@server --username admin
    """
    ssh_target, username = _parse_login_web_args(args)

    print(f"\nConnecting to {ssh_target}...")

    try:
        token = get_magic_link_via_ssh(ssh_target, username)
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Construct the magic link URL
    server_url = infer_server_url(ssh_target)
    magic_link = f"{server_url}/auth/magic/{token}"

    print()
    print("Magic link generated!")
    print()
    print("Open this URL in your browser to log in:")
    print()
    print(f"  {magic_link}")
    print()
    print("Note: This link expires in 5 minutes and can only be used once.")


def _parse_login_web_args(args: list[str]) -> tuple[str, str]:
    """Parse arguments for login --web command.

    Returns:
        Tuple of (ssh_target, username)
    """
    ssh_target = None
    username = "admin"  # Default to admin user

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--web" and i + 1 < len(args):
            # Next argument should be the SSH target
            next_arg = args[i + 1]
            if not next_arg.startswith("-"):
                ssh_target = next_arg
                i += 2
            else:
                i += 1
        elif arg == "--username" and i + 1 < len(args):
            username = args[i + 1]
            i += 2
        elif not arg.startswith("-") and not ssh_target:
            # Positional argument could be SSH target
            ssh_target = arg
            i += 1
        else:
            i += 1

    if not ssh_target:
        print_login_help()
        print(
            "\nError: --web requires an SSH target (e.g., hop3 login --web root@server.com)",
            file=sys.stderr,
        )
        sys.exit(1)

    return ssh_target, username


def handle_login_token(args: list[str], config: Config, printer: RichPrinter) -> None:
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
    context_name = config.get_current_context_name()
    if context_name:
        config.update_context_credentials(api_url=server_url, api_token=token)
    else:
        # No context exists - create a "default" context
        context_name = "default"
        config.add_context(name=context_name, api_url=server_url, api_token=token)

    print(f"\nLogged in as {username}")
    print(f"Credentials saved to context '{context_name}'")


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

    # Try to get URL from current context
    existing_url = config.get_api_url()
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


def _determine_save_url(
    api_url: str | None,
    ssh_target: str,
    token: str,
    config: Config,
    debug_level: int,
) -> tuple[str, dict]:
    """Determine the API URL to save and any extra config kwargs.

    Returns:
        Tuple of (save_url, extra_kwargs)
    """
    extra_kwargs = {}
    if api_url:
        # User explicitly provided URL - use HTTP API
        save_url = api_url
        if debug_level >= 1:
            print(f"[debug] Will use HTTP API at: {api_url}")
        # For HTTPS, verify the connection works with system CA bundle
        if api_url.startswith("https://"):
            config_data = {"api_url": api_url, "api_token": token}
            _verify_https_connection(api_url, token, config, config_data, debug_level)
            if "verify_ssl" in config_data:
                extra_kwargs["verify_ssl"] = config_data["verify_ssl"]
    else:
        # Default: use SSH tunnel for all subsequent commands
        save_url = _build_ssh_url(ssh_target)
        if debug_level >= 1:
            print(f"[debug] Will use SSH tunnel: {save_url}")

    return save_url, extra_kwargs


def handle_login_ssh(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Handle the login --ssh command for getting token via SSH.

    SSH access is the authentication - no username/password needed by default.
    If --username is provided, uses the legacy flow for that specific user.

    Usage:
        hop3 login --ssh user@server                    # Auto-auth (recommended)
        hop3 login --ssh user@server --username admin   # Specific user (legacy)
        hop3 login --ssh user@server --url https://...  # Use HTTP API instead
        hop3 login --ssh user@server -d                 # Show debug info
    """
    ssh_target, username, api_url, debug_level = _parse_login_ssh_args(args)

    if debug_level >= 1:
        print(f"[debug] SSH target: {ssh_target}")
        print(f"[debug] Username: {username or '(auto)'}")
        print(f"[debug] API URL override: {api_url or '(none, will use SSH tunnel)'}")

    print(f"\nConnecting to {ssh_target}...")

    try:
        if username:
            # Legacy flow: get token for specific user
            token = get_token_via_ssh(ssh_target, username)
            display_username = username
        else:
            # New simplified flow: SSH access = admin access
            token = get_ssh_token(ssh_target)
            display_username = "admin"  # Default user created/used by admin:ssh-token
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if debug_level >= 2:
        print(f"[debug] Token received: {token[:20]}...{token[-10:]}")

    # Determine API URL to save
    save_url, extra_kwargs = _determine_save_url(
        api_url, ssh_target, token, config, debug_level
    )

    context_name = config.get_current_context_name()
    if context_name:
        config.update_context_credentials(
            api_url=save_url, api_token=token, **extra_kwargs
        )
    else:
        # No context exists - create a "default" context
        context_name = "default"
        config.add_context(
            name=context_name,
            api_url=save_url,
            api_token=token,
            **extra_kwargs,
        )

    if debug_level >= 1:
        print(f"[debug] Credentials saved to context: {context_name}")

    _print_login_success(display_username, config, context_name)


def _build_ssh_url(ssh_target: str) -> str:
    """Build SSH URL from SSH target.

    Args:
        ssh_target: SSH target (user@host or host)

    Returns:
        SSH URL for the API (e.g., ssh://root@hop3.dev)
    """
    if "@" in ssh_target:
        return f"ssh://{ssh_target}"
    return f"ssh://root@{ssh_target}"


def _parse_login_ssh_args(args: list[str]) -> tuple[str, str | None, str | None, int]:
    """Parse arguments for login --ssh command.

    Returns:
        Tuple of (ssh_target, username, api_url, debug_level)
    """
    ssh_target = None
    username = None
    api_url = None
    debug_level = 0

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--ssh" and i + 1 < len(args):
            ssh_target = args[i + 1]
            i += 2
        elif arg == "--username" and i + 1 < len(args):
            username = args[i + 1]
            i += 2
        elif arg == "--url" and i + 1 < len(args):
            api_url = args[i + 1]
            i += 2
        elif arg.startswith("-d"):
            # Count consecutive 'd's: -d = 1, -dd = 2, -ddd = 3
            debug_level += arg.count("d")
            i += 1
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

    return ssh_target, username, api_url, debug_level


def _verify_https_connection(
    api_url: str,
    token: str,
    config: Config,
    config_data: dict,
    debug_level: int = 0,
) -> None:
    """Verify HTTPS connection works with the system CA bundle.

    If SSL verification fails, offers to disable it for self-signed certificates.

    Args:
        api_url: The HTTPS URL to verify
        token: The API token for authentication
        config: Config object for saving settings
        config_data: Config data dict to update
        debug_level: Debug verbosity level
    """
    import requests  # noqa: PLC0415

    if debug_level >= 1:
        print(f"[debug] Verifying HTTPS connection to {api_url}")

    try:
        # Try to connect with system CA bundle
        response = requests.get(
            f"{api_url.rstrip('/')}/health",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            verify=True,  # Use system CA bundle
        )
        if response.ok:
            print("HTTPS connection verified ✓")
        else:
            print(f"HTTPS connection works (status: {response.status_code})")

    except requests.exceptions.SSLError:
        # Self-signed or untrusted certificate
        print()
        print("The server uses a self-signed or untrusted SSL certificate.")
        print()
        print("Options:")
        print("  1. Use SSH tunnel instead (recommended):")
        print(f"     hop3 login --ssh {_extract_host(api_url)}")
        print()
        print("  2. Disable SSL verification for this server:")

        # Ask user if they want to disable SSL verification (if interactive)
        try:
            if sys.stdin.isatty():
                answer = input("\nDisable SSL verification? [y/N]: ").strip().lower()
                if answer in {"y", "yes"}:
                    config_data["verify_ssl"] = "false"
                    print("SSL verification disabled.")
                    return
        except (EOFError, KeyboardInterrupt):
            pass

        print()
        print("To disable SSL verification later, run:")
        print("  hop3 settings set verify_ssl false")

    except requests.exceptions.RequestException as e:
        if debug_level >= 1:
            print(f"[debug] Connection error: {e}")
        print(f"Warning: Could not verify connection to {api_url}")


def _extract_host(url: str) -> str:
    """Extract user@host from URL for display."""
    from urllib.parse import urlparse  # noqa: PLC0415

    parsed = urlparse(url)
    host = parsed.hostname or url
    return f"root@{host}"


def _handle_ssl_certificate(
    ssh_target: str, server_url: str, config: Config, config_data: dict
) -> None:
    """Handle SSL certificate fetching for HTTPS connections.

    Note: This function is currently unused. For most HTTPS connections,
    the system CA bundle works. For self-signed certs, users should set
    verify_ssl=false.
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


def _print_login_success(username: str, config: Config, context_name: str) -> None:
    """Print success message after login."""
    print(f"\nToken generated for user '{username}'")
    print(f"Credentials saved to context '{context_name}'")
    print("\nWelcome back! Try:")
    print("  hop3 apps           # List applications")
    print("  hop3 auth:whoami    # Check current user")
