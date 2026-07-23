# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""User-facing messages for setup and error states."""

from __future__ import annotations


def show_unconfigured_message(cli_args: list[str]) -> None:
    """
    Show helpful setup instructions when CLI is not configured.

    Args:
        cli_args: The command-line arguments (for context)
    """
    from hop3_cli.core import credential_store  # ruff:ignore[import-outside-top-level]

    # ADR 042: if the operator is logged into servers but none is selected for
    # this command (e.g. two known, no default context), guide them to name one
    # and select it with --context rather than running `hop3 init` from scratch.
    known = credential_store.known_servers()
    if known:
        print("No context selected for this command.\n")
        print("You're logged into these servers:")
        for server in known:
            print(f"  - {server}")
        print("\nName one as a context, then select it by name:")
        print("  hop3 context add prod --server <addr>   # name a server")
        print("  hop3 <command> --context prod           # target it")
        print("\nLog in naming the context to set it as the default target:")
        print("  hop3 login --context prod --ssh root@your-server.com")
        return

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
