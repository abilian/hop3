# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""JSON-RPC controller for Hop3 CLI commands."""

from __future__ import annotations

import contextlib
import json
import traceback
from typing import TYPE_CHECKING

from advanced_alchemy.exceptions import RepositoryError
from litestar import Controller, Request, post
from litestar.response import Response

from hop3 import config
from hop3.commands import Command
from hop3.core.plugins import get_plugin_manager
from hop3.lib import format_diagnosis
from hop3.lib.console import verbosity_context
from hop3.lib.logging import server_log
from hop3.lib.registry import lookup
from hop3.lib.repository_errors import (
    repository_error_diagnosis as _repository_error_diagnosis,
)
from hop3.lib.scanner import scan_package
from hop3.orm import get_session_factory
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
    EnvVarRepository,
    PortClaimRepository,
    RevokedTokenRepository,
    RoleRepository,
    UserRepository,
)
from hop3.server.security.web_auth import current_identity

# Mapping of repository types to their classes for dependency injection
REPOSITORY_TYPES: dict[str, type] = {
    "user_repo": UserRepository,
    "role_repo": RoleRepository,
    "app_repo": AppRepository,
    "addon_credential_repo": AddonCredentialRepository,
    "backup_repo": BackupRepository,
    "env_var_repo": EnvVarRepository,
    "revoked_token_repo": RevokedTokenRepository,
    "port_claim_repo": PortClaimRepository,
}

if TYPE_CHECKING:
    from hop3.lib.types import Json, JsonDict

# Scan and register all CLI commands (including aliases)
scan_package("hop3.commands")


def _build_command_table() -> dict[tuple[str, ...], type[Command]]:
    """
    Build the RPC dispatch table from core + plugin-contributed commands.

    Core commands live in `hop3.commands` (scanned above and found via the
    registry). Plugins contribute additional commands through the
    `cli_commands()` hook — e.g. the addon plugins add `addon <type> <verb>`
    commands such as `addon postgres credentials`. Calling the hook also
    forces plugin loading, so this works regardless of import order.
    """
    table: dict[tuple[str, ...], type[Command]] = {}

    def add(cmd: type[Command]) -> None:
        # Register primary name (ADR 036 D1/D18: name is a tuple of tokens)
        table[cmd.name] = cmd
        # Register aliases (legacy server-side aliases; tuples too)
        for alias in getattr(cmd, "aliases", []):
            table[alias] = cmd

    for command in lookup(Command):
        add(command)

    for contributed in get_plugin_manager().hook.cli_commands():
        for command in contributed or []:
            add(command)

    return table


_commands: dict[tuple[str, ...], type[Command]] = _build_command_table()
commands = _commands

# Maximum command-name depth we're willing to match. Per ADR 036 D3/D12,
# 3 levels is the strong guideline; we allow up to 4 to leave headroom for
# unusual plugin-contributed commands without forcing a hard rejection.
_MAX_COMMAND_DEPTH = 4


def find_command(cli_args: list[str]) -> tuple[type[Command] | None, int]:
    """
    Find the command matching the longest tuple prefix of cli_args.

    Tries longest prefix first: for cli_args = ["addon", "postgres", "diagnose", "mydb"],
    checks ("addon", "postgres", "diagnose", "mydb") → ("addon", "postgres", "diagnose")
    → ("addon", "postgres") → ("addon",). Returns the command class for the first
    match found, plus the number of tokens consumed.

    Returns (None, 0) if nothing matches.
    """
    for n in range(min(len(cli_args), _MAX_COMMAND_DEPTH), 0, -1):
        key = tuple(cli_args[:n])
        if key in _commands:
            return _commands[key], n
    return None, 0


def format_command_name(name: tuple[str, ...]) -> str:
    """Format a command name tuple for human display (e.g., in error messages)."""
    return " ".join(name)


def requires_authentication(command_class: type[Command]) -> bool:
    """
    Check if a command requires authentication.

    Uses the declarative `requires_auth` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if authentication is required, False otherwise
    """
    return getattr(command_class, "requires_auth", True)


def command_needs_username(command_class: type[Command]) -> bool:
    """
    Check if a command needs the authenticated username.

    Uses the declarative `pass_username` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if the command needs the username, False otherwise
    """
    return getattr(command_class, "pass_username", False)


def command_needs_token_info(command_class: type[Command]) -> bool:
    """
    Check if a command needs the full token information.

    Uses the declarative `pass_token_info` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if the command needs token info (jti, exp), False otherwise
    """
    return getattr(command_class, "pass_token_info", False)


def call(
    command_name: tuple[str, ...], args: list[str], extra_args: JsonDict
) -> list[dict]:
    """
    Execute a CLI command with given arguments.

    Args:
        command_name: Tuple of tokens naming the command (e.g., ("config", "set"))
        args: Positional arguments for the command (tokens after the command name)
        extra_args: Keyword arguments for the command (verbosity is extracted as context)

    Returns:
        Command execution result

    Raises:
        ValueError: If command not found or execution fails
    """
    display_name = format_command_name(command_name)
    command_class = commands.get(command_name)
    if command_class is None:
        msg = f"Command '{display_name}' not found"
        server_log.error("Command not found", command=display_name)
        raise ValueError(msg)

    server_log.debug(
        "Creating command instance",
        command=display_name,
        command_class=command_class.__name__,
    )

    # Extract verbosity from extra_args - it's a context parameter, not a command kwarg
    verbosity_val = extra_args.pop("verbosity", 1)
    verbosity = verbosity_val if isinstance(verbosity_val, int) else 1

    # Prepare command kwargs (without verbosity - it's handled via context)
    command_kwargs = extra_args.copy()

    session_factory = get_session_factory()
    db_session = session_factory()
    try:
        class_args: dict = {}

        # Inject db_session if needed (legacy pattern)
        if "db_session" in command_class.__annotations__:
            class_args["db_session"] = db_session
            server_log.debug("Command uses db_session", command=display_name)

        # Inject repositories if needed (new pattern)
        annotations = command_class.__annotations__
        for attr_name, repo_class in REPOSITORY_TYPES.items():
            if attr_name in annotations:
                class_args[attr_name] = repo_class(session=db_session)
                server_log.debug(
                    f"Command uses {attr_name}",
                    command=display_name,
                    repo_type=repo_class.__name__,
                )

        try:
            command = command_class(**class_args)
        except Exception as e:
            error_msg = f"Failed to create command: {e}"
            server_log.error(
                "Failed to create command instance",
                command=display_name,
                error=str(e),
            )
            raise ValueError(error_msg) from e

        try:
            server_log.debug(
                "Calling command.call()",
                command=display_name,
                args=args,
                extra_args_keys=list(command_kwargs.keys()),
                verbosity=verbosity,
            )
            # Set verbosity context for the duration of command execution
            with verbosity_context(verbosity):
                result = command.call(*args, **command_kwargs)
            server_log.debug(
                "Command.call() returned",
                command=display_name,
                result_type=type(result).__name__,
            )
            # Commit any pending changes (if not already committed by command)
            db_session.commit()
        except Exception as e:
            # Rollback on any error to clean up transaction state
            with contextlib.suppress(Exception):
                db_session.rollback()
            error_msg = f"Command execution failed: {e}"
            server_log.error(
                "Command.call() raised exception",
                command=display_name,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise ValueError(error_msg) from e

        return result
    finally:
        # Always close the session, but handle any state errors gracefully
        try:
            db_session.close()
        except Exception as e:
            server_log.warning(
                "Error closing database session",
                command=display_name,
                error=str(e),
            )


class RPCController(Controller):
    """
    JSON-RPC endpoint controller for CLI commands.

    Handles JSON-RPC requests from the Hop3 CLI, executing commands
    on the server with authentication and authorization checks.
    """

    path = "/rpc"

    @post("/", status_code=200)
    async def handle_rpc(self, request: Request, data: dict) -> Response:
        """
        Handle JSON-RPC request.

        Args:
            request: HTTP request
            data: JSON-RPC request data from body

        Returns:
            JSON-RPC response
        """
        # Parse request
        method = data["method"]
        assert method == "cli"

        params = data["params"]
        cli_args = params["cli_args"]
        extra_args = params["extra_args"]
        request_id = data.get("id", 1)

        # Find the command by longest-prefix match (ADR 036 D1/D18).
        # For `hop3 config set FOO=bar`, cli_args = ["config", "set", "FOO=bar"];
        # the command name is the tuple ("config", "set") and args is ["FOO=bar"].
        command_class, n_consumed = find_command(cli_args)
        command_name: tuple[str, ...] = (
            command_class.name if command_class is not None else tuple(cli_args[:1])
        )
        args = cli_args[n_consumed:] if command_class is not None else cli_args[1:]

        display_name = format_command_name(command_name)

        # Log all incoming RPC commands for debugging
        server_log.info(
            "RPC request received",
            command=display_name,
            args=args,
            extra_args_keys=list(extra_args.keys()),
            request_id=request_id,
        )

        # Check authentication (before revealing if command exists)
        auth_error = self._check_authentication(request, command_class)
        if auth_error:
            return auth_error

        # Validate command exists
        if command_class is None:
            return self._build_error_response(
                code=-32601,  # Method not found
                message=f"Command '{display_name}' not found",
                request_id=request_id,
                status_code=404,
            )

        # Prepare arguments and execute
        prepared_args, prepared_extra_args = self._prepare_command_args(
            request, command_class, args, extra_args
        )
        return self._execute_command(
            command_name, prepared_args, prepared_extra_args, request_id
        )

    def _build_error_response(
        self, code: int, message: str, request_id: int, status_code: int = 200
    ) -> Response:
        """
        Build a JSON-RPC error response.

        Args:
            code: JSON-RPC error code
            message: Error message
            request_id: Request ID from the original request
            status_code: HTTP status code (default 200 per JSON-RPC spec)

        Returns:
            JSON-RPC error response
        """
        error_rpc = {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
            "id": request_id,
        }
        return Response(
            content=json.dumps(error_rpc),
            media_type="application/json",
            status_code=status_code,
        )

    def _build_success_response(
        self, result: Json | list[dict], request_id: int
    ) -> Response:
        """
        Build a JSON-RPC success response.

        Args:
            result: Command execution result (can be dict, list, or primitive)
            request_id: Request ID from the original request

        Returns:
            JSON-RPC success response
        """
        result_rpc: dict = {"jsonrpc": "2.0", "result": result, "id": request_id}
        return Response(
            content=json.dumps(result_rpc),
            media_type="application/json",
        )

    def _check_authentication(
        self, request: Request, command_class: type[Command] | None
    ) -> Response | None:
        """
        Check if the request is authenticated when required.

        For security, authentication is checked BEFORE revealing if the command
        exists. This prevents information disclosure about available commands.

        The credential is the stateless signed JWT (``current_identity``),
        accepted from the ``Authorization: Bearer`` header (CLI / API) or the
        ``hop3_auth`` cookie (dashboard) — no server-side session.

        Args:
            request: HTTP request
            command_class: The command class (may be None if not found)

        Returns:
            Error response if authentication failed, None if OK
        """
        authenticated = current_identity(request) is not None

        # Skip authentication enforcement in unsafe testing mode
        if config.HOP3_UNSAFE:
            return None

        # Check if authentication is required
        if command_class is not None and not requires_authentication(command_class):
            return None

        if authenticated:
            return None

        # Authentication failed
        return self._build_error_response(
            code=401,
            message="Authentication required. Use 'hop3 auth login' to authenticate.",
            request_id=1,
            status_code=401,
        )

    def _prepare_command_args(
        self,
        request: Request,
        command_class: type[Command],
        args: list[str],
        extra_args: JsonDict,
    ) -> tuple[tuple, JsonDict]:
        """
        Prepare command arguments by injecting username and token info.

        Args:
            request: HTTP request
            command_class: The command class
            args: Positional arguments
            extra_args: Keyword arguments

        Returns:
            Tuple of (prepared_args, prepared_extra_args)
        """
        prepared_args = tuple(args)
        prepared_extra_args = extra_args.copy()

        # Pass authenticated username to commands that need it
        if command_needs_username(command_class):
            identity = current_identity(request)
            if identity and identity.get("username"):
                prepared_args = (identity["username"], *prepared_args)

        # Pass token information to commands that need it (e.g., logout)
        if command_needs_token_info(command_class):
            auth_header = request.headers.get("authorization", "")
            # RFC 7235: auth-scheme is case-insensitive
            if auth_header[:7].lower() == "bearer ":
                token = auth_header[7:].strip()
                prepared_extra_args["_token"] = token

        return prepared_args, prepared_extra_args

    def _execute_command(
        self,
        command_name: tuple[str, ...],
        args: tuple,
        extra_args: JsonDict,
        request_id: int,
    ) -> Response:
        """
        Execute the command and return appropriate response.

        Args:
            command_name: Tuple of tokens naming the command
            args: Positional arguments (after the command-name tokens)
            extra_args: Keyword arguments
            request_id: Request ID for the response

        Returns:
            JSON-RPC response (success or error)
        """
        display_name = format_command_name(command_name)
        server_log.info(
            "Executing command",
            command=display_name,
            args=args,
            extra_args_keys=list(extra_args.keys()),
        )
        try:
            result = call(command_name, list(args), extra_args)
            server_log.info(
                "Command completed successfully",
                command=display_name,
                result_type=type(result).__name__,
                result_length=len(result) if isinstance(result, (list, dict)) else None,
            )
            return self._build_success_response(result, request_id)
        except ValueError as e:
            server_log.error(
                "Command failed with ValueError",
                command=display_name,
                error=str(e),
            )
            traceback.print_exc()
            return self._build_error_response(
                code=-32602,  # Invalid params
                message=str(e),
                request_id=request_id,
            )
        except RepositoryError as e:
            # Unwrap the advanced_alchemy wrapper into a structured Diagnosis
            # so the CLI can render component/reason/hint instead of a generic
            # "There was an error during data processing" string.
            diag = _repository_error_diagnosis(e)
            error_msg = format_diagnosis(diag)
            server_log.error(
                "Command failed with RepositoryError",
                command=display_name,
                error_type=type(e).__name__,
                reason=diag.reason,
                original_error=str(e.__cause__) if e.__cause__ else None,
            )
            traceback.print_exc()
            return self._build_error_response(
                code=-32603,  # Internal error
                message=error_msg,
                request_id=request_id,
            )
        except Exception as e:
            server_log.error(
                "Command failed with exception",
                command=display_name,
                error_type=type(e).__name__,
                error=str(e),
            )
            traceback.print_exc()
            return self._build_error_response(
                code=-32603,  # Internal error
                message=f"{type(e).__name__}: {e!s}",
                request_id=request_id,
            )


# RepositoryError → Diagnosis helpers live in hop3.lib.repository_errors
# so the CLI `git-hook` path can unwrap them with the same logic. The
# aliases above preserve the names used by existing tests.
