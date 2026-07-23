# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Auth command - show authentication help locally."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .login_cmd import handle_login, handle_logout

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_auth(args: list[str], config: Config, printer: RichPrinter) -> bool:
    """
    Handle the `auth` command.

    `auth login` / `auth logout` are the rich local flows (same handlers as the
    `hop3 login` / `hop3 logout` aliases). Other `auth <verb>` (whoami,
    get-token, ...) are forwarded to the server. Bare `hop3 auth` shows help.
    """
    if args and args[0] == "login":
        handle_login(args[1:], config, printer)
        return True
    if args and args[0] == "logout":
        handle_logout(args[1:], config, printer)
        return True

    # Any other subcommand (whoami, get-token, ...) goes to the server.
    if args and not args[0].startswith("-"):
        return False

    print("""Authentication commands.

SUBCOMMANDS
  auth login       Log in to a server (alias: hop3 login).
  auth logout      Log out and clear the local token (alias: hop3 logout).
  auth whoami      Show the current authenticated user.
  auth get-token   Print an API token for scripts/automation.

EXAMPLES
  # First-time setup (creates admin user via SSH)
  hop3 init --ssh root@your-server.com

  # Log in to an existing server
  hop3 login --ssh root@your-server.com

  # Log in with a URL containing a token (for local dev)
  hop3 login "http://localhost:8000?token=eyJ..."

  # Check the current user (requires server connection)
  hop3 auth whoami

  # Mint a token non-interactively (e.g. CI)
  hop3 auth get-token alice --password-file -
""")
    return True
