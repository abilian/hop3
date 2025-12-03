# Copyright (c) 2024-2025, Abilian SAS
"""Simple client-side script for Hop3.

All the logic is implemented on the server side, this script is just a
thin wrapper around SSH to communicate with the server.
"""

# ruff: noqa: E402

from __future__ import annotations

import base64
import re
import sys
import warnings
from pathlib import Path
from typing import Any

import requests.exceptions
from jsonrpcclient import Error, Ok
from loguru import logger

# Suppress cryptography deprecation warnings from paramiko
# These warnings come from paramiko's use of deprecated TripleDES cipher
warnings.filterwarnings("ignore", category=DeprecationWarning, module="paramiko")
warnings.filterwarnings("ignore", message=".*TripleDES.*")
warnings.filterwarnings("ignore", message=".*CryptographyDeprecationWarning.*")
# Catch all deprecation warnings from cryptography module
try:
    from cryptography.utils import CryptographyDeprecationWarning

    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except ImportError:
    pass

from .arguments import generate_archive
from .client import Client
from .config import Config, get_config
from .console import err
from .flags import parse_flags
from .local_commands import handle_local_command, is_local_command
from .prompts import confirm, show_destructive_warning, type_to_confirm
from .rich_printer import RichPrinter
from .types import JsonDict

logger.remove()
# TODO: enable logging to stderr when properly configured
# logger.add(sys.stderr)


def main():
    args = sys.argv[1:]
    run_command_from_args(args)


def run_command_from_args(cli_args: list[str]) -> None:
    # Parse CLI flags (--json, --quiet, -y, etc.)
    flags, cli_args = parse_flags(cli_args)

    # Create printer with appropriate output mode
    printer = RichPrinter(
        verbose=flags.verbose,
        quiet=flags.quiet,
        json_output=flags.json_output,
    )

    config = load_config()

    if not cli_args:
        cli_args = ["help"]

    # Handle local commands (init, config) that don't need server
    # Check BEFORE help flag conversion so "init --help" works
    if is_local_command(cli_args):
        handled = handle_local_command(cli_args, config, printer)
        if handled:
            return

    # Handle --help and -h flags
    # Convert "hop --help" to "hop help"
    # Convert "hop run --help" to "hop help run"
    cli_args = handle_help_flags(cli_args)

    # Check if CLI is configured before trying to connect to server
    if not config.is_configured():
        show_unconfigured_message(cli_args)
        sys.exit(1)

    # Check for destructive commands and prompt for confirmation
    if not flags.skip_confirm and is_destructive_command(cli_args):
        if not confirm_destructive_action(cli_args, printer):
            sys.exit(0)  # User cancelled

    extra_args = get_extra_args(cli_args)

    # Use Client as context manager to ensure tunnel cleanup
    with Client(config=config, state=None) as client:
        response = None
        try:
            # Ensure extra_args contains only valid keyword arguments of correct types
            validated_extra_args: dict[str, Any] = {
                k: v
                for k, v in extra_args.items()
                if isinstance(k, str) and v is not None
            }
            response = client.rpc("cli", cli_args, **validated_extra_args)
        except requests.exceptions.SSLError:
            err(
                f"SSL certificate verification failed for {client.rpc_url}.\n\n"
                "Options:\n"
                "  1. Trust this server's certificate:\n"
                "     hop3 settings set ssl_cert /path/to/server.crt\n\n"
                "  2. Disable SSL verification (less secure):\n"
                "     hop3 settings set verify_ssl false"
            )
            sys.exit(1)
        except requests.exceptions.ConnectionError as e:
            # Check if it's actually an SSL error wrapped in ConnectionError
            error_str = str(e).lower()
            if "ssl" in error_str or "certificate" in error_str:
                err(
                    f"SSL certificate verification failed for {client.rpc_url}.\n\n"
                    "Options:\n"
                    "  1. Trust this server's certificate:\n"
                    "     hop3 settings set ssl_cert /path/to/server.crt\n\n"
                    "  2. Disable SSL verification (less secure):\n"
                    "     hop3 settings set verify_ssl false"
                )
            else:
                err(
                    f"Could not connect to the Hop3 server at {client.rpc_url}.\n"
                    "Is it running?"
                )
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            err(f"HTTP error while connecting to the Hop3 server:\n{e}")
            sys.exit(1)
        except Exception as e:
            err(f"Error while executing command:\n{e}")
            sys.exit(1)

        match response:
            case Ok(result=result):
                # Handle auth:login specially - save token automatically
                if cli_args and cli_args[0] == "auth:login":
                    handle_login_response(result, config, printer)
                elif cli_args == ["help"] and not printer.json_output:
                    # Inject local commands into help output
                    result = inject_local_commands_into_help(result)
                    printer.print(result)
                else:
                    printer.print(result)
            case Error(message=message):
                err(f"Error:\n{message}")
                sys.exit(1)
            case None:
                pass

        # Flush JSON output if in JSON mode
        if printer.json_output:
            printer.flush_json()


def is_destructive_command(cli_args: list[str]) -> bool:
    """Check if the command is destructive (requires confirmation).

    Args:
        cli_args: Command-line arguments

    Returns:
        True if command is destructive, False otherwise
    """
    if not cli_args:
        return False

    command = cli_args[0]

    # List of destructive commands that require confirmation
    destructive_commands = {
        "app:destroy",
        "destroy",  # Alias for app:destroy
        "backup:delete",
        "services:destroy",
    }

    return command in destructive_commands


def confirm_destructive_action(cli_args: list[str], printer: RichPrinter) -> bool:
    """Prompt user to confirm a destructive action.

    Args:
        cli_args: Command-line arguments
        printer: Printer for output (for JSON mode detection)

    Returns:
        True if user confirmed, False if cancelled
    """
    if printer.json_output:
        # In JSON mode, auto-confirm (user should use -y flag)
        return True

    command = cli_args[0]
    args = cli_args[1:]

    # app:destroy or destroy command - requires type-to-confirm
    if command in {"app:destroy", "destroy"}:
        if not args:
            # No app name provided, let server handle error
            return True

        app_name = args[0]
        show_destructive_warning(
            "destroy",
            f"app '{app_name}'",
            "All files, data, and configuration will be permanently deleted.",
        )
        return type_to_confirm(f"Type '{app_name}' to confirm:", app_name)

    # backup:delete command
    if command == "backup:delete":
        if not args:
            return True

        backup_id = args[0]
        show_destructive_warning(
            "delete",
            f"backup '{backup_id}'",
            "This backup cannot be recovered once deleted.",
        )
        return confirm("Are you sure you want to delete this backup?")

    # services:destroy command
    if command == "services:destroy":
        if not args:
            return True

        addon_name = args[0]
        show_destructive_warning(
            "destroy",
            f"service '{addon_name}'",
            "All data in this service will be permanently deleted.",
        )
        return type_to_confirm(f"Type '{addon_name}' to confirm:", addon_name)

    # Unknown destructive command (shouldn't happen)
    return confirm("This action cannot be undone. Continue?")


def handle_login_response(
    result: list[dict], config: Config, printer: RichPrinter
) -> None:
    """Handle auth:login response - extract and save token, then print modified output.

    Args:
        result: The RPC response from auth:login
        config: The config object to save the token to
        printer: Printer for output
    """
    # JWT token pattern (3 base64url segments separated by dots)
    jwt_pattern = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

    token = None
    modified_result = []
    found_token = False

    # Keywords that indicate manual token save instructions
    skip_keywords = [
        "your api token",
        "save this token",
        "config file",
        "api_token =",
        "environment variable",
        "export hop3_api_token",
    ]

    for item in result:
        if item.get("t") == "text":
            text = item.get("text", "")

            # Check if this text contains a JWT token
            match = jwt_pattern.search(text)
            if match and not found_token:
                token = match.group(0)
                found_token = True
                # Skip the line containing the JWT token itself
                continue

            # Skip all manual instruction messages (before or after token)
            if any(keyword in text.lower() for keyword in skip_keywords):
                continue

            # Keep other text messages (success message, empty lines)
            modified_result.append(item)
        else:
            # Keep non-text messages (tables, errors, etc.)
            modified_result.append(item)

    # Save token if found
    if token:
        try:
            config.save({"api_token": token})
            # Add success message about saving the token
            modified_result.append({
                "t": "text",
                "text": f"\nAPI token saved to {config.config_file}",
            })
            modified_result.append({
                "t": "text",
                "text": "You can now use hop3 commands without additional authentication.",
            })
        except Exception as e:
            modified_result.append({
                "t": "error",
                "text": f"Failed to save token to config: {e}",
            })
            modified_result.append({
                "t": "text",
                "text": f"\nYour API token: {token}",
            })
            modified_result.append({
                "t": "text",
                "text": f"Please save it manually to {config.config_file or '~/.config/hop3-cli/config.toml'}",
            })

    # Print the modified result
    printer.print(modified_result)


def handle_help_flags(args: list[str]) -> list[str]:
    """Convert --help/-h flags to help command invocations.

    Examples:
        ["--help"] -> ["help"]
        ["-h"] -> ["help"]
        ["run", "--help"] -> ["help", "run"]
        ["run", "-h"] -> ["help", "run"]
        ["run", "myapp", "--help"] -> ["help", "run"]  # help for run, not run with --help

    Args:
        args: Command-line arguments

    Returns:
        Modified arguments with --help converted to help command
    """
    if not args:
        return args

    # Check if --help or -h is anywhere in the args
    if "--help" in args or "-h" in args:
        # Remove --help and -h from args
        filtered_args = [arg for arg in args if arg not in {"--help", "-h"}]

        if not filtered_args:
            # Just "--help" with no command -> show general help
            return ["help"]
        # "command --help" -> "help command"
        # Only use the first argument as the command name
        return ["help", filtered_args[0]]

    return args


#
# Ad-hoc functions to generate extra arguments for commands.
# TODO: refactor properly.
#
def get_extra_args(args: list[str]) -> JsonDict:
    """Generate a dictionary of extra arguments."""
    command = args[0]
    match command:
        case "deploy":
            # args[0]="deploy", args[1]=app_name, args[2]=directory
            directory = Path(args[2]) if len(args) > 2 else Path()
            return {
                "repository": pack_repository(directory),
            }
        case _:
            return {}


def pack_repository(directory: Path = Path()) -> str:
    tar_gz = generate_archive(directory)
    return base64.b64encode(tar_gz).decode("ascii")


def load_config() -> Config:
    """Load configuration from the standard user location."""
    return get_config()


def inject_local_commands_into_help(result: list[dict]) -> list[dict]:
    """Inject local CLI commands into the help output from the server.

    The local commands (init, login, settings) are handled by the CLI
    and don't exist on the server, so we need to add them to the help
    output so users can discover them.

    The server may return help as a single text block with newlines,
    so we need to handle that format.

    Args:
        result: The help response from the server

    Returns:
        Modified result with local commands injected
    """
    from .local_commands import LOCAL_COMMANDS_INFO

    modified_result = []

    for item in result:
        if item.get("t") != "text":
            modified_result.append(item)
            continue

        text = item.get("text", "")

        # Check if this is a multi-line text block containing COMMANDS
        if "\n" in text and "COMMANDS" in text:
            # Process line by line
            lines = text.split("\n")
            new_lines = []
            in_commands_section = False
            injected_commands = set()

            for line in lines:
                # Check if entering COMMANDS section
                if line.strip() == "COMMANDS":
                    in_commands_section = True
                    new_lines.append(line)
                    continue

                # Check if leaving COMMANDS section (empty line or new section header)
                if in_commands_section and line.strip() and not line.startswith("  "):
                    # Inject remaining local commands before leaving section
                    for local_cmd in sorted(LOCAL_COMMANDS_INFO.keys()):
                        if local_cmd not in injected_commands:
                            desc = LOCAL_COMMANDS_INFO[local_cmd]
                            new_lines.append(f"  {local_cmd:16} {desc}")
                            injected_commands.add(local_cmd)
                    in_commands_section = False

                # If in commands section, check if we need to inject before this command
                if in_commands_section and line.startswith("  ") and line.strip():
                    parts = line.strip().split(None, 1)
                    if parts:
                        current_cmd = parts[0]
                        # Inject local commands that come before this one alphabetically
                        for local_cmd in sorted(LOCAL_COMMANDS_INFO.keys()):
                            if (
                                local_cmd not in injected_commands
                                and local_cmd < current_cmd
                            ):
                                desc = LOCAL_COMMANDS_INFO[local_cmd]
                                new_lines.append(f"  {local_cmd:16} {desc}")
                                injected_commands.add(local_cmd)

                new_lines.append(line)

            # If still in commands section at end, inject remaining
            if in_commands_section:
                for local_cmd in sorted(LOCAL_COMMANDS_INFO.keys()):
                    if local_cmd not in injected_commands:
                        desc = LOCAL_COMMANDS_INFO[local_cmd]
                        # Find the last command line and insert after it
                        insert_idx = len(new_lines)
                        for i in range(len(new_lines) - 1, -1, -1):
                            if new_lines[i].startswith("  ") and new_lines[i].strip():
                                insert_idx = i + 1
                                break
                        new_lines.insert(insert_idx, f"  {local_cmd:16} {desc}")
                        injected_commands.add(local_cmd)

            modified_result.append({"t": "text", "text": "\n".join(new_lines)})
        else:
            modified_result.append(item)

    return modified_result


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
