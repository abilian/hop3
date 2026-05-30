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
from .core.alias_registry import (  # noqa: E402
    build_registry,
    cached_subcommand_index,
    load_user_aliases_from_config,
    resolve_aliases,
)
from .core.app_scope import is_app_scoped  # noqa: E402
from .core.resolution import format_trace, resolve_app  # noqa: E402
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
    try:
        run_command_from_args(args)
    except KeyboardInterrupt:
        # ADR 036 D16: SIGINT exits with 130 (POSIX convention: 128+SIGINT).
        # We swallow the traceback here so Ctrl-C doesn't dump a Python stack
        # at the user; the exit code lets scripts detect it.
        print(file=sys.stderr)  # newline so the next shell prompt isn't glued
        sys.exit(ExitCode.INTERRUPTED)


def run_command_from_args(cli_args: list[str]) -> None:
    """Run a CLI command from the given arguments."""
    flags, cli_args = parse_flags(cli_args)
    # Bridge --no-input into an env var so prompt-bearing helpers (which
    # don't receive flags directly) can refuse to read from a tty. See
    # hop3_cli.ui.prompts.is_no_input.
    if flags.no_input:
        import os  # noqa: PLC0415

        os.environ["HOP3_NO_INPUT"] = "1"
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

    # ADR 036 D9: expand aliases before local/server dispatch, unless the user
    # passed --no-alias. Aliases fire on the first token only and respect the
    # collision-with-subcommand rule.
    if not flags.no_alias:
        cli_args = _apply_aliases(cli_args, config, printer, flags)

    # Handle local commands (init, config) that don't need server
    if is_local_command(cli_args):
        if flags.verbosity >= 2:
            printer.print_debug("Handling as local command")
        if handle_local_command(cli_args, config, printer):
            return

    cli_args = handle_help_flags(cli_args)
    cli_args = _resolve_and_inject_app(cli_args, flags, config, printer)
    _update_printer_scope(printer, config, cli_args)
    _check_prerequisites(cli_args, config, printer, flags)

    if flags.verbosity >= 2:
        printer.print_debug("Executing RPC command...")

    extra_args = _get_extra_args_safe(cli_args, flags.verbosity)
    _execute_rpc_command(cli_args, config, extra_args, printer)


def _exit_no_app_resolved(resolution, cli_args: list[str], n_consumed: int) -> None:
    """Print a helpful error and exit when an app-scoped command has no app.

    Per ADR 036 D7: list the sources we tried and suggest concrete fixes.
    Exits with code 3 (resolution error per D16). Goes to stderr (D19).
    """
    cmd_display = " ".join(cli_args[:n_consumed]) or "this command"
    sources_tried = "\n  ".join(f"- {entry}" for entry in resolution.trace)
    print(
        f"Error: '{cmd_display}' requires an app, but no app could be resolved.\n"
        f"\nTried (in order):\n  {sources_tried}\n"
        f"\nTo fix, choose one:\n"
        f"  hop3 use <app>                # set sticky app for this context\n"
        f"  export HOP3_APP=<app>         # set for this shell session\n"
        f"  echo <app> > .hop3-app        # set for this directory\n"
        f"  hop3 {cmd_display} --app <app>   # one-time override",
        file=sys.stderr,
    )
    sys.exit(ExitCode.RESOLUTION_ERROR)


def _apply_aliases(
    cli_args: list[str],
    config: Config,
    printer: RichPrinter,
    flags,
) -> list[str]:
    """Expand the first-token alias (if any) per ADR 036 D9.

    Loads the effective alias registry (core + plugin + user) once per
    invocation, runs the resolver, and returns the rewritten argv. The
    subcommand-collision check is consulted via the cached command list.
    """
    user_aliases = load_user_aliases_from_config(config.config_file)
    # Warn about user/core collisions only on bare `hop3` — avoid noise on
    # every invocation. For now, we don't warn at all; `hop3 aliases` reports.
    registry = build_registry(user_aliases=user_aliases, warn_to_stderr=False)
    subcommand_index = cached_subcommand_index()
    rewritten, fired = resolve_aliases(
        cli_args, registry, known_subcommands_of_namespace=subcommand_index
    )
    if fired and flags.verbosity >= 2:
        printer.print_debug(
            f"[alias] {fired.source_token!r} -> "
            f"{' '.join(fired.expansion)!r} (source: {fired.origin})"
        )
    return rewritten


def _resolve_and_inject_app(
    cli_args: list[str],
    flags,
    config: Config,
    printer: RichPrinter,
) -> list[str]:
    """Resolve the effective app (ADR 036 D7) and inject it into cli_args.

    For app-scoped commands, the resolved app is injected as the first
    positional argument after the command-name tokens. The server's dispatcher
    and command handlers continue to expect the app as first positional.

    If `--why` is set, print the resolution trace and exit (diagnostic-only,
    the command is NOT executed — running it would turn `hop3 deploy --why`
    into an actual deploy, which is a footgun).
    If no app can be resolved for an app-scoped command that was invoked
    without an explicit positional, we do NOT error here — the server-side
    command still has its own "missing argument" handling. We just leave
    cli_args untouched.
    """
    scoped, n_consumed = is_app_scoped(cli_args)
    if not scoped and not flags.why:
        return cli_args

    # Resolve only when needed (app-scoped or --why was requested).
    resolution = resolve_app(cli_app=flags.app, config=config)

    if flags.why:
        # Always print the resolution trace to stderr, regardless of verbosity
        # or json_output setting. `--why` is an explicit user request for
        # diagnostic output and shouldn't be gated.
        print(format_trace(resolution), file=sys.stderr)
        # Diagnostic-only: don't run the command. See docstring.
        sys.exit(ExitCode.SUCCESS)

    if not scoped:
        return cli_args

    # ADR 036 D10: if the command is app-scoped, no app resolved, and the user
    # didn't pass a positional that might serve as the app, give a structured
    # client-side error explaining what to do — instead of letting the server
    # return a bare "Usage: hop foo <app>" string.
    if not resolution.resolved:
        remaining = cli_args[n_consumed:]
        no_positional = not remaining or remaining[0].startswith("-")
        if no_positional:
            _exit_no_app_resolved(resolution, cli_args, n_consumed)
        return cli_args

    # If the user already provided a positional app (e.g., `hop3 logs myapp`),
    # don't inject again — the explicit positional wins.
    remaining = cli_args[n_consumed:]
    already_has_positional = bool(remaining) and not remaining[0].startswith("-")
    # Exception: for `run <cmd>`, the first positional is the command to run,
    # not an app — so injection is still needed. Per ADR 036 D5 the app is a
    # flag; we detect this case by checking the command path.
    command_tuple = tuple(cli_args[:n_consumed])
    first_positional_is_app = command_tuple != ("run",)

    if already_has_positional and first_positional_is_app and flags.app is None:
        return cli_args

    # Inject the resolved app as the first positional after the command name.
    # `resolution.resolved` was checked above, so `resolution.app` is non-None here.
    resolved_app = resolution.app
    assert resolved_app is not None
    injected = [*cli_args[:n_consumed], resolved_app, *cli_args[n_consumed:]]
    if flags.verbosity >= 2:
        printer.print_debug(
            f"[app resolution] injected {resolution.app!r} "
            f"(source: {resolution.source})"
        )
    return injected


def _update_printer_scope(
    printer: RichPrinter, config: Config, cli_args: list[str]
) -> None:
    """Populate printer scope so summary lines carry a [context / app] prefix.

    We best-effort-extract the app from the argv after app resolution has
    run (it's injected as the first positional for app-scoped commands).
    For non-app-scoped commands we leave app as None and the prefix falls
    back to just [context] (or nothing if no context is active).
    """
    context_name = config.get_current_context_name()
    app_name: str | None = None
    scoped, n_consumed = is_app_scoped(cli_args)
    if scoped:
        remaining = cli_args[n_consumed:]
        if remaining and not remaining[0].startswith("-"):
            app_name = remaining[0]
    printer.set_scope(context=context_name, app=app_name)


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
        sys.exit(ExitCode.RESOLUTION_ERROR)
    except ValueError as e:
        # ValueError from get_extra_args means the user passed something the
        # CLI couldn't parse (bad --input flag, missing password file, etc.).
        err(f"Invalid input: {e}")
        sys.exit(ExitCode.USAGE_ERROR)
    except PermissionError as e:
        err(f"Permission denied: {e}")
        sys.exit(ExitCode.AUTHZ_ERROR)


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

    # Prompt for confirmation on destructive commands. `--yes`/`-y`/`--force`
    # bypass entirely; `--confirm=<name>` and `--no-input` flow through.
    if not flags.skip_confirm and is_destructive_command(cli_args):
        if not confirm_destructive_action(cli_args, printer, config, flags=flags):
            # ADR 036 D16: declined confirmation (or non-tty without --yes/--confirm)
            # has its own exit code so scripts can distinguish "user said no" from
            # other failures.
            sys.exit(ExitCode.CONFIRMATION_DECLINED)


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

    # Commands that can run without authentication. Space-separated tuples per
    # ADR 036 D1.
    #
    # Matching rules:
    # - ("help",), ("version",): match as a prefix (help or any subcommand of help).
    # - ("auth", "login"), ("auth", "register"): match as a prefix (positional args OK).
    # - ("auth",): exact match only — bare `hop3 auth` shows help without auth,
    #   but `hop3 auth whoami` / `auth logout` require auth.
    prefix_no_auth: set[tuple[str, ...]] = {
        ("help",),
        ("version",),
        ("auth", "login"),
        ("auth", "register"),
    }
    exact_no_auth: set[tuple[str, ...]] = {
        ("auth",),
    }

    full = tuple(cli_args)
    if full in exact_no_auth:
        return False
    for n in range(min(len(cli_args), 3), 0, -1):
        if tuple(cli_args[:n]) in prefix_no_auth:
            return False
    return True


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
            sys.exit(ExitCode.NETWORK_ERROR)
        except TimeoutError:
            err("Connection to the Hop3 server timed out.")
            sys.exit(ExitCode.NETWORK_ERROR)
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
    sys.exit(ExitCode.NETWORK_ERROR)


def _handle_connection_error(e: Exception, rpc_url: str) -> None:
    """Handle connection errors, including wrapped SSL errors."""
    error_str = str(e).lower()
    if "ssl" in error_str or "certificate" in error_str:
        _handle_ssl_error(rpc_url)
    else:
        err(f"Could not connect to the Hop3 server at {rpc_url}.\nIs it running?")
        sys.exit(ExitCode.NETWORK_ERROR)


def load_config() -> Config:
    """Load configuration from the standard user location."""
    return get_config()


def verify_authentication(config: Config) -> None:
    """Verify that the current authentication token is valid.

    Makes a lightweight auth whoami call to check if the token works.

    Args:
        config: The CLI configuration

    Raises:
        AuthenticationError: If authentication is invalid or verification fails.
    """
    from hop3_cli.exceptions import AuthenticationError  # noqa: PLC0415

    try:
        with Client(config=config) as client:
            response = client.rpc("cli", ["auth", "whoami"])
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
