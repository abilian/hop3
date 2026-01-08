# Copyright (c) 2024-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Simple client-side script for Hop3.

All the logic is implemented on the server side, this script is just a
thin wrapper around SSH to communicate with the server.
"""

from __future__ import annotations

# IMPORTANT: Suppress warnings BEFORE any imports that might trigger paramiko
# paramiko uses deprecated TripleDES cipher which triggers CryptographyDeprecationWarning
# These filters must be applied before paramiko is imported (via sshtunnel -> rpc)
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="paramiko")
warnings.filterwarnings("ignore", message=".*TripleDES.*")
warnings.filterwarnings("ignore", message=".*CryptographyDeprecationWarning.*")
try:
    from cryptography.utils import CryptographyDeprecationWarning

    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except ImportError:
    pass

import sys  # noqa: E402
from typing import Any  # noqa: E402

import requests.exceptions  # noqa: E402
from jsonrpcclient import Error, Ok  # noqa: E402
from loguru import logger  # noqa: E402

from .commands import (  # noqa: E402
    confirm_destructive_action,
    get_extra_args,
    handle_help_flags,
    handle_local_command,
    is_destructive_command,
    is_local_command,
    parse_flags,
)
from .config import Config, get_config  # noqa: E402
from .exit_codes import ExitCode  # noqa: E402
from .rpc import Client, handle_response  # noqa: E402
from .ui import (  # noqa: E402
    RichPrinter,
    err,
    show_unauthenticated_message,
    show_unconfigured_message,
)

logger.remove()
# TODO: enable logging to stderr when properly configured
# logger.add(sys.stderr)


def main():
    """Entry point for the CLI."""
    args = sys.argv[1:]
    run_command_from_args(args)


def run_command_from_args(cli_args: list[str]) -> None:
    """Run a CLI command from the given arguments."""
    # Parse CLI flags (--json, --quiet, -y, etc.)
    flags, cli_args = parse_flags(cli_args)

    # Create printer with appropriate output mode
    printer = RichPrinter(
        verbose=flags.verbose,
        quiet=flags.quiet,
        json_output=flags.json_output,
        debug=flags.debug,
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
    cli_args = handle_help_flags(cli_args)

    # Check prerequisites (config, auth, destructive confirmation)
    _check_prerequisites(cli_args, config, printer, flags)

    # Execute the RPC command
    extra_args = get_extra_args(cli_args, verbosity=flags.verbosity)
    response = _execute_rpc_command(cli_args, config, extra_args)

    # Handle the response
    handle_response(response, cli_args, config, printer)


def _check_prerequisites(
    cli_args: list[str], config: Config, printer: RichPrinter, flags
) -> None:
    """Check all prerequisites before executing a command."""
    # Skip all checks for commands that don't require authentication
    if not requires_authentication(cli_args):
        return

    # Check if CLI is configured
    if not config.is_configured():
        show_unconfigured_message(cli_args)
        sys.exit(ExitCode.AUTH_ERROR)

    # Check authentication
    if not config.is_authenticated():
        show_unauthenticated_message()
        sys.exit(ExitCode.AUTH_ERROR)

    # For destructive commands, verify token is valid BEFORE asking for confirmation
    if is_destructive_command(cli_args):
        if not verify_authentication(config):
            show_unauthenticated_message()
            sys.exit(ExitCode.AUTH_ERROR)

    # Prompt for confirmation on destructive commands
    if not flags.skip_confirm and is_destructive_command(cli_args):
        if not confirm_destructive_action(cli_args, printer):
            sys.exit(ExitCode.SUCCESS)  # User cancelled


def requires_authentication(cli_args: list[str]) -> bool:
    """Check if the command requires authentication.

    Note: Most no-auth commands (version, auth) are now handled locally
    and won't reach this check. This remains as a safety net for RPC commands.

    See also: is_help_command() in commands/help.py which checks if help output
    should be augmented with local commands (different purpose).
    """
    if not cli_args:
        return False

    command = cli_args[0]
    no_auth_commands = {"help", "version", "auth", "auth:login", "auth:register"}
    return command not in no_auth_commands


def _execute_rpc_command(cli_args: list[str], config: Config, extra_args: dict) -> Any:
    """Execute RPC command and handle connection errors."""
    with Client(config=config) as client:
        try:
            validated_extra_args: dict[str, Any] = {
                k: v
                for k, v in extra_args.items()
                if isinstance(k, str) and v is not None
            }
            return client.rpc("cli", cli_args, **validated_extra_args)
        except requests.exceptions.SSLError:
            _handle_ssl_error(client.rpc_url)
        except requests.exceptions.ConnectionError as e:
            _handle_connection_error(e, client.rpc_url)
        except requests.exceptions.HTTPError as e:
            err(f"HTTP error while connecting to the Hop3 server:\n{e}")
            sys.exit(ExitCode.CONNECTION_ERROR)
        except TimeoutError:
            err("Connection to the Hop3 server timed out.")
            sys.exit(ExitCode.TIMEOUT_ERROR)
        except Exception as e:
            err(f"Error while executing command:\n{e}")
            sys.exit(ExitCode.GENERAL_ERROR)


def _handle_ssl_error(rpc_url: str) -> None:
    """Handle SSL certificate verification errors."""
    err(
        f"SSL certificate verification failed for {rpc_url}.\n\n"
        "Options:\n"
        "  1. Trust this server's certificate:\n"
        "     hop3 settings set ssl_cert /path/to/server.crt\n\n"
        "  2. Disable SSL verification (less secure):\n"
        "     hop3 settings set verify_ssl false"
    )
    sys.exit(ExitCode.CONNECTION_ERROR)


def _handle_connection_error(e: Exception, rpc_url: str) -> None:
    """Handle connection errors, including wrapped SSL errors."""
    error_str = str(e).lower()
    if "ssl" in error_str or "certificate" in error_str:
        _handle_ssl_error(rpc_url)
    else:
        err(f"Could not connect to the Hop3 server at {rpc_url}.\nIs it running?")
        sys.exit(ExitCode.CONNECTION_ERROR)


def load_config() -> Config:
    """Load configuration from the standard user location."""
    return get_config()


def verify_authentication(config: Config) -> bool:
    """Verify that the current authentication token is valid.

    Makes a lightweight auth:whoami call to check if the token works.

    Args:
        config: The CLI configuration

    Returns:
        True if authenticated, False otherwise
    """
    try:
        with Client(config=config) as client:
            response = client.rpc("cli", ["auth:whoami"])
            match response:
                case Ok():
                    return True
                case Error():
                    return False
                case _:
                    return False
    except Exception:
        return False
