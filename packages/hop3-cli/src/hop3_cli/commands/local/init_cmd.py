# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Init command - bootstrap a new server connection."""

from __future__ import annotations

import getpass
import sys
from typing import TYPE_CHECKING

from ._argv import parse_local_args, usage_failure
from .help_text import print_init_help
from .login_cmd import record_server_login
from .ssh_ops import BootstrapError, create_admin_via_ssh, infer_server_url

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_init(args: list[str], config: Config, printer: RichPrinter) -> None:
    """
    Handle the init command for bootstrapping server connection.

    Usage:
        hop3 init --ssh user@server
        hop3 init --ssh user@server --context dev
        hop3 init --ssh user@server --username admin --email admin@example.com
        echo "password" | hop3 init --ssh user@server --username admin \
            --email admin@example.com --password-stdin
    """
    parsed = _parse_init_args(args, config)
    if parsed is None:
        return  # Help was shown

    ssh_target, username, email, server_url, password_stdin, auto_yes = parsed

    # Infer the server URL from the SSH target if still unknown.
    if not server_url:
        server_url = infer_server_url(ssh_target)
        # Only prompt on an interactive tty. With --password-stdin (or any
        # non-tty, e.g. CI), stdin carries the password — prompting here would
        # consume that line and leave the password empty ("Password cannot be
        # empty"). Infer silently in that case.
        if not auto_yes and not password_stdin and sys.stdin.isatty():
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

    # ADR 042: the token goes to the credential store, the server to the
    # context `--context` names (parsed globally), else `default`.
    record_server_login(config, server_url, token)
    _print_init_success(username, server_url)


#: The usage line printed with every refusal of the init argv.
INIT_USAGE = "Usage: hop3 init --ssh <user@server> [options]  (see hop3 init --help)"


def _parse_init_args(
    args: list[str], config: Config
) -> tuple[str, str | None, str | None, str | None, bool, bool] | None:
    """
    Parse arguments for init command.

    Returns:
        Tuple of (ssh_target, username, email, server_url, password_stdin, auto_yes)
        or None if help was shown
    """
    if "--help" in args or "-h" in args:
        print_init_help()
        return None
    parsed = parse_local_args(
        args,
        usage=INIT_USAGE,
        value_flags=frozenset({"--ssh", "--username", "--email", "--url"}),
        switches=frozenset({"--password-stdin", "--yes", "-y"}),
    )
    ssh_target = parsed.get("--ssh")
    if not ssh_target:
        usage_failure("--ssh is required.", INIT_USAGE)
    username = parsed.get("--username")
    email = parsed.get("--email")
    server_url = parsed.get("--url")
    password_stdin = "--password-stdin" in parsed.switches
    # `-y` is a global flag, so it normally arrives on the config.
    auto_yes = bool({"--yes", "-y"} & parsed.switches) or config.assume_yes()

    return (
        ssh_target,
        username,
        email,
        server_url,
        password_stdin,
        auto_yes,
    )


def _gather_init_credentials(
    username: str | None, email: str | None, *, password_stdin: bool
) -> tuple[str, str, str]:
    """
    Gather username, email, and password for init command.

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


def _print_init_success(username: str, server_url: str) -> None:
    """Print success message after init."""
    print(f"\nAdmin user '{username}' created successfully.")
    print(f"Token stored for {server_url}")
    print("\nYou're all set! Try:")
    print("  hop3 apps           # List applications")
    print("  hop3 auth whoami    # Check current user")
