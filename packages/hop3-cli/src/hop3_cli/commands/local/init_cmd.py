# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Init command - bootstrap a new server connection."""

from __future__ import annotations

import getpass
import sys
from typing import TYPE_CHECKING

from .help_text import print_init_help
from .login_cmd import _handle_ssl_certificate
from .ssh_ops import BootstrapError, create_admin_via_ssh, infer_server_url

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_init(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """Handle the init command for bootstrapping server connection.

    Usage:
        hop3 init --ssh user@server
        hop3 init --ssh user@server --context dev
        hop3 init --ssh user@server --username admin --email admin@example.com
        echo "password" | hop3 init --ssh user@server --username admin \
            --email admin@example.com --password-stdin
    """
    parsed = _parse_init_args(args)
    if parsed is None:
        return True  # Help was shown

    ssh_target, username, email, server_url, password_stdin, auto_yes, context_name = (
        parsed
    )

    # Infer server URL from SSH target if not provided
    if not server_url:
        server_url = infer_server_url(ssh_target)
        if not auto_yes:
            response = input(f"Server URL [{server_url}]: ").strip()
            if response:
                server_url = response

    # Gather credentials
    username, email, password = _gather_init_credentials(
        username, email, password_stdin=password_stdin
    )

    # Execute via SSH
    print(f"\nConnecting to {ssh_target}...")

    try:
        token = create_admin_via_ssh(ssh_target, username, email, password)
    except BootstrapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Save to context if specified, otherwise to current context or legacy format
    if context_name:
        # Create a new context with the credentials
        config.add_context(
            name=context_name,
            api_url=server_url,
            api_token=token,
        )
        config.set_global_context(context_name)
        saved_to_context = True
    else:
        # Try to save to current context, fall back to legacy format
        saved_to_context = config.update_context_credentials(
            api_url=server_url, api_token=token
        )
        if not saved_to_context:
            # Also handle SSL certificate for legacy format
            config_data = {"api_url": server_url, "api_token": token}
            _handle_ssl_certificate(ssh_target, server_url, config, config_data)
            config.save(config_data)

    _print_init_success(username, config, context_name, saved_to_context)
    return True


def _parse_init_args(
    args: list[str],
) -> tuple[str, str | None, str | None, str | None, bool, bool, str | None] | None:
    """Parse arguments for init command.

    Returns:
        Tuple of (ssh_target, username, email, server_url, password_stdin, auto_yes, context_name)
        or None if help was shown
    """
    ssh_target = None
    username = None
    email = None
    server_url = None
    password_stdin = False
    auto_yes = False
    context_name = None

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
        elif arg == "--context" and i + 1 < len(args):
            context_name = args[i + 1]
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

    return ssh_target, username, email, server_url, password_stdin, auto_yes, context_name


def _gather_init_credentials(
    username: str | None, email: str | None, *, password_stdin: bool
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


def _print_init_success(
    username: str,
    config: Config,
    context_name: str | None = None,
    saved_to_context: bool = False,
) -> None:
    """Print success message after init."""
    print(f"\nAdmin user '{username}' created successfully.")
    if context_name:
        print(f"Created and switched to context '{context_name}'")
    elif saved_to_context:
        current_context = config.get_current_context_name()
        print(f"Credentials saved to context '{current_context}'")
    else:
        print(f"Configuration saved to {config.config_file}")
    print("\nYou're all set! Try:")
    print("  hop3 apps           # List applications")
    print("  hop3 auth:whoami    # Check current user")
