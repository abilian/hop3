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
    flags, cli_args = parse_flags(cli_args)
    printer = RichPrinter(
        verbose=flags.verbose,
        quiet=flags.quiet,
        json_output=flags.json_output,
        debug=flags.debug,
    )
    config = load_config()

    if flags.context:
        config.set_context_override(flags.context)

    if flags.verbosity >= 2:
        _print_debug_info(printer, cli_args, config, flags)

    cli_args = cli_args or ["help"]

    # Handle local commands (init, config) that don't need server
    if is_local_command(cli_args):
        if flags.verbosity >= 2:
            printer.print_debug("Handling as local command")
        if handle_local_command(cli_args, config, printer):
            return

    cli_args = handle_help_flags(cli_args)
    _check_prerequisites(cli_args, config, printer, flags)

    if flags.verbosity >= 2:
        printer.print_debug("Executing RPC command...")

    extra_args = _get_extra_args_safe(cli_args, flags.verbosity)
    _execute_rpc_command(cli_args, config, extra_args, printer)


def _print_debug_info(printer: RichPrinter, cli_args: list[str], config, flags) -> None:
    """Print debug information about the current command."""
    printer.print_debug(f"Command: {' '.join(cli_args) if cli_args else '(none)'}")
    printer.print_debug(f"Verbosity: {flags.verbosity}")

    context_name = config.get_current_context_name()
    if context_name:
        context = config.get_current_context()
        protected_marker = " [protected]" if context and context.protected else ""
        printer.print_debug(f"Context: {context_name}{protected_marker}")

    api_url = config.get_api_url() or "(not configured)"
    printer.print_debug(f"API URL: {api_url}")


def _get_extra_args_safe(cli_args: list[str], verbosity: int) -> dict:
    """Get extra args with error handling."""
    try:
        return get_extra_args(cli_args, verbosity=verbosity)
    except FileNotFoundError as e:
        err(f"File or directory not found: {e}")
        sys.exit(ExitCode.GENERAL_ERROR)
    except ValueError as e:
        err(f"Invalid input: {e}")
        sys.exit(ExitCode.GENERAL_ERROR)
    except PermissionError as e:
        err(f"Permission denied: {e}")
        sys.exit(ExitCode.GENERAL_ERROR)


def _check_prerequisites(
    cli_args: list[str], config: Config, printer: RichPrinter, flags
) -> None:
    """Check all prerequisites before executing a command."""
    from hop3_cli.exceptions import AuthenticationError  # noqa: PLC0415

    # Skip all checks for commands that don't require authentication
    if not requires_authentication(cli_args):
        return

    # Check if CLI is configured
    if not config.is_configured():
        show_unconfigured_message(cli_args)
        sys.exit(ExitCode.AUTH_ERROR)

    # Check authentication - try auto-auth via SSH if not authenticated
    if not config.is_authenticated():
        try:
            _try_auto_authenticate(config, printer)
        except AuthenticationError:
            show_unauthenticated_message()
            sys.exit(ExitCode.AUTH_ERROR)

    # For destructive commands, verify token is valid BEFORE asking for confirmation
    if is_destructive_command(cli_args):
        try:
            verify_authentication(config)
        except AuthenticationError:
            # Token might be expired - try auto-auth via SSH
            try:
                _try_auto_authenticate(config, printer)
            except AuthenticationError:
                show_unauthenticated_message()
                sys.exit(ExitCode.AUTH_ERROR)

    # Prompt for confirmation on destructive commands
    if not flags.skip_confirm and is_destructive_command(cli_args):
        if not confirm_destructive_action(cli_args, printer, config):
            sys.exit(ExitCode.SUCCESS)  # User cancelled


def _try_auto_authenticate(config: Config, printer: RichPrinter) -> None:
    """Try to authenticate automatically via SSH if available.

    Raises:
        AuthenticationError: If auto-auth is not available or fails.
    """
    from urllib.parse import urlparse  # noqa: PLC0415

    from hop3_cli.commands.local.ssh_ops import (  # noqa: PLC0415
        BootstrapError,
        get_ssh_token,
    )
    from hop3_cli.exceptions import AuthenticationError  # noqa: PLC0415

    api_url = config.get_api_url()
    if not api_url:
        msg = "No API URL configured"
        raise AuthenticationError(msg)

    parsed = urlparse(api_url)
    if parsed.scheme not in {"ssh", "ssh+http"}:
        msg = f"Auto-auth requires SSH URL (got {parsed.scheme}://)"
        raise AuthenticationError(msg)

    # We have SSH access - try auto-auth
    ssh_user = parsed.username or config.get("ssh_user", "root")
    ssh_host = parsed.hostname
    ssh_target = f"{ssh_user}@{ssh_host}"

    if printer.verbosity >= 1:
        printer.print_debug(f"Auto-authenticating via SSH to {ssh_target}...")

    try:
        token = get_ssh_token(ssh_target)
    except BootstrapError as e:
        if printer.verbosity >= 1:
            printer.print_debug(f"Auto-auth failed: {e}")
        msg = f"SSH authentication to {ssh_target} failed: {e}"
        raise AuthenticationError(msg) from e

    config.update_context_token(token)
    if printer.verbosity >= 1:
        printer.print_debug("Auto-authentication successful")


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


def _execute_rpc_command(
    cli_args: list[str],
    config: Config,
    extra_args: dict,
    printer: RichPrinter,
) -> None:
    """Execute RPC command, handle response, and manage connection lifecycle.

    The response handling is done inside the Client context to keep SSH tunnels
    alive for streaming responses.
    """
    with Client(config=config) as client:
        # Debug: show connection info
        if printer.verbosity >= 2:
            if client.using_ssh_tunnel:
                printer.print_debug(f"Using SSH tunnel to {config.get('api_url')}")
                printer.print_debug(f"RPC endpoint: {client.rpc_url}")
            else:
                printer.print_debug(f"Direct connection to {client.rpc_url}")

        try:
            validated_extra_args: dict[str, Any] = {
                k: v
                for k, v in extra_args.items()
                if isinstance(k, str) and v is not None
            }
            response = client.rpc("cli", cli_args, **validated_extra_args)

            # Get tunnel port if using SSH tunnel (for streaming support)
            tunnel_port = None
            if client.tunnel:
                tunnel_port = client.tunnel.local_bind_port

            # Handle response INSIDE the context to keep tunnel alive for streaming
            handle_response(
                response, cli_args, config, printer, tunnel_port=tunnel_port
            )

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


def verify_authentication(config: Config) -> None:
    """Verify that the current authentication token is valid.

    Makes a lightweight auth:whoami call to check if the token works.

    Args:
        config: The CLI configuration

    Raises:
        AuthenticationError: If authentication is invalid or verification fails.
    """
    from hop3_cli.exceptions import AuthenticationError  # noqa: PLC0415

    try:
        with Client(config=config) as client:
            response = client.rpc("cli", ["auth:whoami"])
            match response:
                case Ok():
                    return
                case Error(message=message):
                    msg = f"Authentication failed: {message}"
                    raise AuthenticationError(msg)
                case _:
                    msg = "Authentication verification failed: unexpected response"
                    raise AuthenticationError(msg)
    except AuthenticationError:
        raise
    except Exception as e:
        msg = f"Authentication verification failed: {e}"
        raise AuthenticationError(msg) from e
