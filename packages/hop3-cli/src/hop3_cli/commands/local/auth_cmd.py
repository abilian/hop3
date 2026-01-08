# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Auth command - show authentication help locally."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


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
