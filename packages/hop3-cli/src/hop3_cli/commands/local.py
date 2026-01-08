# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands handled locally.

These commands are processed by the CLI without requiring an RPC call to the server:
- init: Bootstrap a new server connection via SSH
- login: Authenticate (via SSH or username/password)
- settings: Manage local CLI configuration
- version: Show CLI version
- auth: Show authentication help
"""

from __future__ import annotations

import getpass
import re
import shlex
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


# Commands that are handled locally (not sent to server via RPC)
# Format: command_name -> description
LOCAL_COMMANDS_INFO = {
    "init": "Initialize connection to a Hop3 server via SSH.",
    "login": "Authenticate to a server.",
    "settings": "Manage local CLI settings (server URL, token, SSL).",
    "version": "Show CLI version.",
    "auth": "Authentication commands.",
}

LOCAL_COMMANDS = set(LOCAL_COMMANDS_INFO.keys())

# Path to hop3-server on the remote server
HOP_SERVER_PATH = "/home/hop3/venv/bin/hop3-server"


def is_local_command(args: list[str]) -> bool:
    """Check if the command should be handled locally."""
    if not args:
        return False

    command = args[0]

    # Handle --version and -V flags as local command
    if command in {"--version", "-V"}:
        return True

    return command in LOCAL_COMMANDS


def handle_local_command(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle a local command.

    Returns:
        True if the command was handled, False if it should be sent to server
    """
    if not args:
        return False

    command = args[0]
    cmd_args = args[1:]

    if command == "init":
        return handle_init(cmd_args, config, printer)
    if command == "login":
        return handle_login(cmd_args, config, printer)
    if command == "settings":
        return handle_settings(cmd_args, config, printer)
    if command in {"version", "--version", "-V"}:
        return handle_version(cmd_args, config, printer)
    if command == "auth":
        return handle_auth(cmd_args, config, printer)

    return False


def handle_version(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the version command - show CLI version locally."""
    from importlib.metadata import version

    try:
        cli_version = version("hop3-cli")
    except Exception:
        cli_version = "unknown"

    print(f"hop3-cli {cli_version}")
    return True


def handle_auth(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the auth command - show auth help locally."""
    # If there are subcommand args, this isn't just "hop auth"
    if args and not args[0].startswith("-"):
        # This is something like "hop auth:login" which should go to server
        return False

    # Check for help flag
    if args and args[0] in {"--help", "-h"}:
        pass  # Fall through to show help

    print("""Authentication commands.

SUBCOMMANDS
  auth:login       Authenticate and receive an API token.
  auth:register    Register a new user account.
  auth:whoami      Show current authenticated user.
  auth:logout      Invalidate the current session token.

LOCAL COMMANDS
  login            Authenticate to a server (local handling).
  init             Initialize connection and create admin user.

EXAMPLES
  # First-time setup (creates admin user via SSH)
  hop3 init --ssh root@your-server.com

  # Login to existing server
  hop3 login --ssh root@your-server.com

  # Login with URL containing token (for local dev)
  hop3 login "http://localhost:8000?token=eyJ..."

  # Check current user (requires server connection)
  hop3 auth:whoami
""")
    return True


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
        from urllib.parse import parse_qs, urlparse

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
    from hop3_cli.rpc import Client

    print(f"\nAuthenticating as {username}...")

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
    from jsonrpcclient import Error, Ok

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
    jwt_pattern = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

    for item in result:
        if item.get("t") == "text":
            text = item.get("text", "")
            match = jwt_pattern.search(text)
            if match:
                return match.group(0)
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
    import os

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
    from hop3_cli.config import Config as TempConfig
    from hop3_cli.rpc import Client

    # Create a temporary config for verification
    temp_config = TempConfig(
        data={"api_url": server_url, "api_token": token},
        config_file=None,
    )

    print(f"Verifying connection to {server_url}...")

    try:
        with Client(config=temp_config) as client:
            from jsonrpcclient import Error, Ok

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

    from urllib.parse import urlparse

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


def handle_init(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the init command for bootstrapping server connection.

    Usage:
        hop3 init --ssh user@server
        hop3 init --ssh user@server --username admin --email admin@example.com
        echo "password" | hop3 init --ssh user@server --username admin \
            --email admin@example.com --password-stdin
    """
    parsed = _parse_init_args(args)
    if parsed is None:
        return True  # Help was shown

    ssh_target, username, email, server_url, password_stdin, auto_yes = parsed

    # Infer server URL from SSH target if not provided
    if not server_url:
        server_url = infer_server_url(ssh_target)
        if not auto_yes:
            response = input(f"Server URL [{server_url}]: ").strip()
            if response:
                server_url = response

    # Gather credentials
    username, email, password = _gather_init_credentials(
        username, email, password_stdin
    )

    # Execute via SSH
    print(f"\nConnecting to {ssh_target}...")

    try:
        token = create_admin_via_ssh(ssh_target, username, email, password)
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Prepare and save config
    config_data = {"api_url": server_url, "api_token": token}
    _handle_ssl_certificate(ssh_target, server_url, config, config_data)
    config.save(config_data)

    _print_init_success(username, config)
    return True


def _parse_init_args(
    args: list[str],
) -> tuple[str, str | None, str | None, str | None, bool, bool] | None:
    """Parse arguments for init command.

    Returns:
        Tuple of (ssh_target, username, email, server_url, password_stdin, auto_yes)
        or None if help was shown
    """
    ssh_target = None
    username = None
    email = None
    server_url = None
    password_stdin = False
    auto_yes = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--ssh" and i + 1 < len(args):
            ssh_target = args[i + 1]
            i += 2
        elif arg == "--username" and i + 1 < len(args):
            username = args[i + 1]
            i += 2
        elif arg == "--email" and i + 1 < len(args):
            email = args[i + 1]
            i += 2
        elif arg == "--server" and i + 1 < len(args):
            server_url = args[i + 1]
            i += 2
        elif arg == "--password-stdin":
            password_stdin = True
            i += 1
        elif arg in {"--yes", "-y"}:
            auto_yes = True
            i += 1
        elif arg in {"--help", "-h"}:
            print_init_help()
            return None
        else:
            i += 1

    if not ssh_target:
        print_init_help()
        print("\nError: --ssh argument is required", file=sys.stderr)
        sys.exit(1)

    # Type narrowing: ssh_target is str after the check above
    assert ssh_target is not None

    return ssh_target, username, email, server_url, password_stdin, auto_yes


def _gather_init_credentials(
    username: str | None, email: str | None, password_stdin: bool
) -> tuple[str, str, str]:
    """Gather username, email, and password for init command.

    Returns:
        Tuple of (username, email, password)
    """
    if not username:
        username = input("Admin username: ").strip()
        if not username:
            print("Error: Username cannot be empty", file=sys.stderr)
            sys.exit(1)

    if not email:
        email = input("Admin email: ").strip()
        if not email:
            print("Error: Email cannot be empty", file=sys.stderr)
            sys.exit(1)

    if password_stdin:
        password = sys.stdin.read().strip()
    else:
        password = getpass.getpass("Admin password: ")
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("Error: Passwords do not match", file=sys.stderr)
            sys.exit(1)

    if not password:
        print("Error: Password cannot be empty", file=sys.stderr)
        sys.exit(1)

    return username, email, password


def _print_init_success(username: str, config: Config) -> None:
    """Print success message after init."""
    print(f"\nAdmin user '{username}' created successfully.")
    print(f"Configuration saved to {config.config_file}")
    print("\nYou're all set! Try:")
    print("  hop3 apps           # List applications")
    print("  hop3 auth:whoami    # Check current user")


def handle_settings(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the settings command for managing local CLI settings.

    Usage:
        hop3 settings show
        hop3 settings set <key> <value>
        hop3 settings get <key>
    """
    if not args or args[0] in {"--help", "-h"}:
        print_settings_help()
        return True

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand == "show":
        return settings_show(config, printer)
    if subcommand == "set":
        return settings_set(sub_args, config, printer)
    if subcommand == "get":
        return settings_get(sub_args, config, printer)
    print(f"Unknown settings subcommand: {subcommand}", file=sys.stderr)
    print_settings_help()
    sys.exit(1)

    return True


def settings_show(config: Config, printer: RichPrinter) -> bool:
    """Show current CLI settings."""
    import os

    print(f"Config file: {config.config_file}\n")

    # Show dev mode status
    dev_mode = os.environ.get("HOP3_DEV_MODE", "").lower() in {"true", "1", "yes"}
    if dev_mode:
        print("Developer mode: ENABLED (HOP3_DEV_MODE)")
        print("  Localhost default: http://localhost:8000\n")

    if config.data:
        print("Current settings:")
        for key, value in sorted(config.data.items()):
            # Mask token for security
            if "token" in key.lower() and value:
                display_value = value[:20] + "..." if len(value) > 20 else value
            else:
                display_value = value
            print(f"  {key} = {display_value}")
    else:
        print("No settings configured. Using defaults.")

    print("\nDefaults:")
    for key, value in sorted(config.defaults.items()):
        if key not in config.data:
            print(f"  {key} = {value}")

    # Show configuration status
    print(f"\nConfigured: {config.is_configured()}")
    if not config.is_configured():
        print("\nTo configure, run:")
        print("  hop3 init --ssh root@your-server.com")

    return True


def settings_set(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Set a CLI settings value."""
    if len(args) < 2:
        print("Usage: hop3 settings set <key> <value>", file=sys.stderr)
        sys.exit(1)

    key = args[0]
    value = args[1]

    # Normalize key aliases
    if key == "server":
        key = "api_url"
    if key == "token":
        key = "api_token"

    # Convert boolean-like values for verify_ssl
    if key == "verify_ssl":
        value = str(value.lower() in {"true", "yes", "1"}).lower()

    config.save({key: value})
    print(
        f"Set {key} = {value[:20] + '...' if 'token' in key and len(value) > 20 else value}"
    )
    print(f"Saved to {config.config_file}")

    return True


def settings_get(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Get a CLI settings value."""
    if not args:
        print("Usage: hop3 settings get <key>", file=sys.stderr)
        sys.exit(1)

    key = args[0]
    # Handle aliases
    if key == "server":
        key = "api_url"
    if key == "token":
        key = "api_token"

    try:
        value = config[key]
        print(value)
    except KeyError:
        print(f"Key not found: {key}", file=sys.stderr)
        sys.exit(1)

    return True


class BootstrapError(Exception):
    """Error during bootstrap process."""


def create_admin_via_ssh(
    ssh_target: str, username: str, email: str, password: str
) -> str:
    """Create admin user via SSH and return the token.

    Args:
        ssh_target: SSH target (user@host)
        username: Admin username
        email: Admin email
        password: Admin password

    Returns:
        The API token

    Raises:
        BootstrapError: If the command fails
    """
    # Build the remote command - run as hop3 user to ensure correct file ownership
    # The database is created on first access, so running as hop3 ensures it's owned by hop3:hop3
    hop3_cmd = f"{HOP_SERVER_PATH} admin:create {shlex.quote(username)} {shlex.quote(email)} --password-stdin"
    remote_cmd = f"su - hop3 -c {shlex.quote(hop3_cmd)}"

    # Run via SSH
    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        input=password,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        msg = f"Failed to create admin: {error_msg}"
        raise BootstrapError(msg)

    # Parse token from output
    token = extract_token(result.stdout)
    if not token:
        msg = f"Could not extract token from server response:\n{result.stdout}"
        raise BootstrapError(msg)

    return token


def get_token_via_ssh(ssh_target: str, username: str) -> str:
    """Get a new token for existing user via SSH.

    Args:
        ssh_target: SSH target (user@host)
        username: Username to get token for

    Returns:
        The API token

    Raises:
        BootstrapError: If the command fails
    """
    # Run as hop3 user for consistency and proper file access
    hop3_cmd = f"{HOP_SERVER_PATH} admin:token {shlex.quote(username)}"
    remote_cmd = f"su - hop3 -c {shlex.quote(hop3_cmd)}"

    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        msg = f"Failed to get token: {error_msg}"
        raise BootstrapError(msg)

    token = extract_token(result.stdout)
    if not token:
        msg = f"Could not extract token from server response:\n{result.stdout}"
        raise BootstrapError(msg)

    return token


def fetch_and_save_certificate(
    ssh_target: str, server_url: str, config: Config
) -> str | None:
    """Fetch the server's SSL certificate via SSH and save it locally.

    Args:
        ssh_target: SSH target (user@host)
        server_url: The HTTPS URL of the server
        config: Config object to determine where to save the certificate

    Returns:
        Path to the saved certificate file, or None if failed
    """
    from urllib.parse import urlparse

    # Extract hostname from server URL
    parsed = urlparse(server_url)
    hostname = parsed.hostname
    port = parsed.port or 443

    if not hostname:
        return None

    # Use openssl to fetch the certificate via SSH
    # This runs on the server and returns the certificate
    remote_cmd = (
        f"openssl s_client -connect {hostname}:{port} "
        f"-servername {hostname} </dev/null 2>/dev/null | "
        f"openssl x509 2>/dev/null"
    )

    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    cert_content = result.stdout.strip()

    # Validate it looks like a certificate
    if "-----BEGIN CERTIFICATE-----" not in cert_content:
        return None

    # Save the certificate next to the config file
    config_dir = config.config_file.parent if config.config_file else None
    if not config_dir:
        return None

    # Use hostname for the certificate filename
    safe_hostname = hostname.replace(".", "_").replace(":", "_")
    cert_path = config_dir / f"{safe_hostname}.crt"

    # Ensure directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    # Write the certificate
    cert_path.write_text(cert_content + "\n")

    return str(cert_path)


def extract_token(output: str) -> str | None:
    """Extract JWT token from command output.

    Args:
        output: Command output containing the token

    Returns:
        The JWT token or None if not found
    """
    # JWT token pattern (3 base64url segments separated by dots)
    jwt_pattern = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

    match = jwt_pattern.search(output)
    if match:
        return match.group(0)
    return None


def infer_server_url(ssh_target: str) -> str:
    """Infer HTTPS URL from SSH target.

    Args:
        ssh_target: SSH target (user@host or host)

    Returns:
        HTTPS URL for the server
    """
    # user@host -> host
    if "@" in ssh_target:
        host = ssh_target.split("@")[1]
    else:
        host = ssh_target

    # Strip SSH port if present
    if ":" in host:
        host = host.split(":")[0]

    return f"https://{host}"


def print_init_help():
    """Print help for the init command."""
    print("""Usage: hop3 init --ssh <user@server> [options]

Bootstrap a new Hop3 server connection by creating an admin user.

Options:
  --ssh <user@server>    SSH target for the server (required)
  --username <name>      Admin username (prompted if not provided)
  --email <email>        Admin email (prompted if not provided)
  --server <url>         Server URL (inferred from SSH target if not provided)
  --password-stdin       Read password from stdin
  -y, --yes              Skip confirmation prompts

Examples:
  # Interactive setup
  hop3 init --ssh root@my-server.com

  # Non-interactive setup
  echo "secretpass" | hop3 init --ssh root@my-server.com \\
    --username admin --email admin@example.com --password-stdin -y
""")


def print_settings_help():
    """Print help for the settings command."""
    print("""Usage: hop3 settings <subcommand> [args]

Manage local CLI settings.

Subcommands:
  show              Show current settings
  set <key> <value> Set a settings value
  get <key>         Get a settings value

Keys:
  server (api_url)  Server URL (e.g., https://my-server.com)
  token (api_token) API authentication token
  ssl_cert          Path to trusted certificate file (for self-signed certs)
  verify_ssl        Verify SSL certificates (true/false, default: true)

Examples:
  hop3 settings show
  hop3 settings set server https://my-server.com
  hop3 settings set token eyJhbGciOiJI...
  hop3 settings set ssl_cert ~/server.crt  # Trust a specific certificate
  hop3 settings set verify_ssl false       # Disable SSL verification (less secure)
  hop3 settings get server
""")


def print_login_help():
    """Print help for the login command."""
    print("""Usage: hop3 login [options]

Authenticate to a Hop3 server.

Authentication methods:
  <url>?token=<token>    URL with embedded token (easiest for local dev)
  --ssh <user@server>    SSH-based authentication (for remote servers)
  --token <token>        Use a pre-generated token (with --server)
  (default)              Username/password authentication

Options:
  --ssh <user@server>    Use SSH-based authentication
  --token <token>        Use a pre-generated API token
  --server <url>         Server URL (for --token, prompted if not configured)
  --username <name>      Username (for password auth, prompted if not provided)

Examples:
  # URL with embedded token (easiest for local development)
  hop3-server admin:create admin admin@example.com  # Get token
  hop3 login "http://localhost:8000?token=eyJ..."

  # SSH-based login (for remote servers)
  hop3 login --ssh root@my-server.com

  # Password-based login (server must be configured)
  hop3 login

Note: For first-time setup (creating a new admin user), use:
  hop3 init --ssh root@my-server.com
""")
