# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Local CLI commands that don't require server communication.

These commands run entirely on the client side:
- init: Bootstrap a new server connection (with optional SSH)
- config: Manage local CLI configuration
- login --ssh: Get token via SSH for existing user
"""

from __future__ import annotations

import getpass
import re
import shlex
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config
    from .rich_printer import RichPrinter


# Commands that are handled locally (not sent to server)
LOCAL_COMMANDS = {"init", "config"}

# Commands that may be handled locally depending on arguments
CONDITIONAL_LOCAL_COMMANDS = {"login"}


def is_local_command(args: list[str]) -> bool:
    """Check if the command should be handled locally."""
    if not args:
        return False

    command = args[0]

    # Always local commands
    if command in LOCAL_COMMANDS:
        return True

    # Conditional local commands (check for --ssh flag)
    if command in CONDITIONAL_LOCAL_COMMANDS:
        return "--ssh" in args

    return False


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
    if command == "config":
        return handle_config(cmd_args, config, printer)
    if command == "login" and "--ssh" in args:
        return handle_login_ssh(cmd_args, config, printer)

    return False


def handle_login_ssh(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the login --ssh command for getting token via SSH.

    Usage:
        hop3 login --ssh user@server
        hop3 login --ssh user@server --username admin
    """
    # Check for help first
    if "--help" in args or "-h" in args:
        print_login_ssh_help()
        return True

    # Parse arguments
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
        print_login_ssh_help()
        print("\nError: --ssh argument is required", file=sys.stderr)
        sys.exit(1)

    # Infer server URL from SSH target if not provided
    if not server_url:
        server_url = infer_server_url(ssh_target)
        response = input(f"Server URL [{server_url}]: ").strip()
        if response:
            server_url = response

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

    # Save configuration
    config.save({
        "api_url": server_url,
        "api_token": token,
    })

    print(f"Token generated for user '{username}'")
    print(f"\nConfiguration saved to {config.config_file}")
    print("\nWelcome back! Try:")
    print("  hop3 status       # Check server status")
    print("  hop3 apps         # List applications")

    return True


def handle_init(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the init command for bootstrapping server connection.

    Usage:
        hop3 init --ssh user@server
        hop3 init --ssh user@server --username admin --email admin@example.com
        echo "password" | hop3 init --ssh user@server --username admin --email admin@example.com --password-stdin
    """
    # Parse arguments
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
        elif arg in ("--yes", "-y"):
            auto_yes = True
            i += 1
        elif arg in ("--help", "-h"):
            print_init_help()
            return True
        else:
            i += 1

    if not ssh_target:
        print_init_help()
        print("\nError: --ssh argument is required", file=sys.stderr)
        sys.exit(1)

    # Infer server URL from SSH target if not provided
    if not server_url:
        server_url = infer_server_url(ssh_target)
        if not auto_yes:
            response = input(f"Server URL [{server_url}]: ").strip()
            if response:
                server_url = response

    # Prompt for username and email if not provided
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

    # Get password
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

    # Execute via SSH
    print(f"\nConnecting to {ssh_target}...")

    try:
        token = create_admin_via_ssh(ssh_target, username, email, password)
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Save configuration
    config.save({
        "api_url": server_url,
        "api_token": token,
    })

    print(f"Admin user '{username}' created successfully.")
    print(f"\nConfiguration saved to {config.config_file}")
    print("\nYou're all set! Try:")
    print("  hop3 status       # Check server status")
    print("  hop3 apps         # List applications")

    return True


def handle_config(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the config command for managing local configuration.

    Usage:
        hop3 config show
        hop3 config set <key> <value>
        hop3 config get <key>
    """
    if not args or args[0] in ("--help", "-h"):
        print_config_help()
        return True

    subcommand = args[0]
    sub_args = args[1:]

    if subcommand == "show":
        return config_show(config, printer)
    if subcommand == "set":
        return config_set(sub_args, config, printer)
    if subcommand == "get":
        return config_get(sub_args, config, printer)
    print(f"Unknown config subcommand: {subcommand}", file=sys.stderr)
    print_config_help()
    sys.exit(1)

    return True


def config_show(config: Config, printer: RichPrinter) -> bool:
    """Show current configuration."""
    print(f"Config file: {config.config_file}\n")

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

    return True


def config_set(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Set a configuration value."""
    if len(args) < 2:
        print("Usage: hop3 config set <key> <value>", file=sys.stderr)
        sys.exit(1)

    key = args[0]
    value = args[1]

    # Validate key
    valid_keys = {"api_url", "api_token", "server", "ssh_user"}
    # Also allow 'server' as alias for 'api_url'
    if key == "server":
        key = "api_url"
    if key == "token":
        key = "api_token"

    config.save({key: value})
    print(
        f"Set {key} = {value[:20] + '...' if 'token' in key and len(value) > 20 else value}"
    )
    print(f"Saved to {config.config_file}")

    return True


def config_get(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Get a configuration value."""
    if not args:
        print("Usage: hop3 config get <key>", file=sys.stderr)
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
    # Build the remote command
    remote_cmd = f"hop-server admin:create {shlex.quote(username)} {shlex.quote(email)} --password-stdin"

    # Run via SSH
    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        input=password.encode(),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        raise BootstrapError(f"Failed to create admin: {error_msg}")

    # Parse token from output
    token = extract_token(result.stdout)
    if not token:
        raise BootstrapError(
            f"Could not extract token from server response:\n{result.stdout}"
        )

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
    remote_cmd = f"hop-server admin:token {shlex.quote(username)}"

    result = subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        raise BootstrapError(f"Failed to get token: {error_msg}")

    token = extract_token(result.stdout)
    if not token:
        raise BootstrapError(
            f"Could not extract token from server response:\n{result.stdout}"
        )

    return token


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


def print_config_help():
    """Print help for the config command."""
    print("""Usage: hop3 config <subcommand> [args]

Manage local CLI configuration.

Subcommands:
  show              Show current configuration
  set <key> <value> Set a configuration value
  get <key>         Get a configuration value

Keys:
  server (api_url)  Server URL (e.g., https://my-server.com)
  token (api_token) API authentication token

Examples:
  hop3 config show
  hop3 config set server https://my-server.com
  hop3 config set token eyJhbGciOiJI...
  hop3 config get server
""")


def print_login_ssh_help():
    """Print help for the login --ssh command."""
    print("""Usage: hop3 login --ssh <user@server> [options]

Get an API token for an existing user via SSH.

This command is useful when:
- You lost your token and need a new one
- You're setting up the CLI on a new machine
- You need to rotate your token

Options:
  --ssh <user@server>    SSH target for the server (required)
  --username <name>      Username (prompted if not provided)
  --server <url>         Server URL (inferred from SSH target if not provided)

Examples:
  # Interactive
  hop3 login --ssh root@my-server.com

  # Non-interactive
  hop3 login --ssh root@my-server.com --username admin --server https://my-server.com

Note: For first-time setup (creating a new admin user), use:
  hop3 init --ssh root@my-server.com
""")
