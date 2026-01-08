# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Settings command - manage local CLI settings."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from hop3_cli.commands.local.help_text import print_settings_help

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


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
