# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""User-facing messages for setup and error states."""

from __future__ import annotations


def show_unconfigured_message(cli_args: list[str]) -> None:
    """Show helpful setup instructions when CLI is not configured.

    Args:
        cli_args: The command-line arguments (for context)
    """
    print("Hop3 CLI is not configured.\n")
    print("To get started, connect to your Hop3 server:\n")
    print("  hop3 init --ssh root@your-server.com\n")
    print("This will:")
    print("  - Create an admin user on the server")
    print("  - Save the server URL and authentication token")
    print("  - Configure SSL certificate trust\n")
    print("If you already have a user account:")
    print("  hop3 login --ssh root@your-server.com\n")
    print("Or configure manually:")
    print("  hop3 settings set server https://your-server.com")
    print("  hop3 settings set token <your-api-token>\n")
    print("For developers running a local server:")
    print("  export HOP3_DEV_MODE=true")
    print("  hop3 help")


def show_unauthenticated_message() -> None:
    """Show helpful login instructions when CLI is not authenticated."""
    print("Authentication required.\n")
    print("To authenticate, use one of the following methods:")
    print("  1. Login: hop3 login <url-with-token>")
    print("  2. Init:  hop3 init --ssh root@your-server.com\n")
    print("After logging in, save the token to ~/.config/hop3-cli/config.toml")
    print("or set the HOP3_API_TOKEN environment variable.")
