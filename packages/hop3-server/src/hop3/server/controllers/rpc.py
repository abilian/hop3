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
from hop3.lib.console import verbosity_context
from hop3.lib.logging import server_log
from hop3.lib.registry import lookup
from hop3.lib.scanner import scan_package
from hop3.orm import get_session_factory
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
    EnvVarRepository,
    RevokedTokenRepository,
    RoleRepository,
    UserRepository,
)
from hop3.server.security.tokens import validate_token

# Mapping of repository types to their classes for dependency injection
REPOSITORY_TYPES: dict[str, type] = {
    "user_repo": UserRepository,
    "role_repo": RoleRepository,
    "app_repo": AppRepository,
    "addon_credential_repo": AddonCredentialRepository,
    "backup_repo": BackupRepository,
    "env_var_repo": EnvVarRepository,
    "revoked_token_repo": RevokedTokenRepository,
}

if TYPE_CHECKING:
    from hop3.lib.types import Json, JsonDict

# Scan and register all CLI commands (including aliases)
scan_package("hop3.commands")
_commands: dict[str, type[Command]] = {}
for command in lookup(Command):
    # Register primary name
    _commands[command.name] = command
    # Register aliases
    for alias in getattr(command, "aliases", []):
        _commands[alias] = command
commands = _commands


def requires_authentication(command_class: type[Command]) -> bool:
    """Check if a command requires authentication.

    Uses the declarative `requires_auth` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if authentication is required, False otherwise
    """
    return getattr(command_class, "requires_auth", True)


def command_needs_username(command_class: type[Command]) -> bool:
    """Check if a command needs the authenticated username.

    Uses the declarative `pass_username` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if the command needs the username, False otherwise
    """
    return getattr(command_class, "pass_username", False)


def command_needs_token_info(command_class: type[Command]) -> bool:
    """Check if a command needs the full token information.

    Uses the declarative `pass_token_info` class attribute.

    Args:
        command_class: The command class

    Returns:
        True if the command needs token info (jti, exp), False otherwise
    """
    return getattr(command_class, "pass_token_info", False)


def call(command_name: str, args: list[str], extra_args: JsonDict):
    """Execute a CLI command with given arguments.

    Args:
        command_name: Name of the command to execute
        args: Positional arguments for the command
        extra_args: Keyword arguments for the command (verbosity is extracted as context)

    Returns:
        Command execution result

    Raises:
        ValueError: If command not found or execution fails
    """
    command_class = commands.get(command_name)
    if command_class is None:
        msg = f"Command {command_name} not found"
        server_log.error("Command not found", command=command_name)
        raise ValueError(msg)

    server_log.debug(
        "Creating command instance",
        command=command_name,
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
            server_log.debug("Command uses db_session", command=command_name)

        # Inject repositories if needed (new pattern)
        annotations = command_class.__annotations__
        for attr_name, repo_class in REPOSITORY_TYPES.items():
            if attr_name in annotations:
                class_args[attr_name] = repo_class(session=db_session)
                server_log.debug(
                    f"Command uses {attr_name}",
                    command=command_name,
                    repo_type=repo_class.__name__,
                )

        try:
            command = command_class(**class_args)
        except Exception as e:
            error_msg = f"Failed to create command: {e}"
            server_log.error(
                "Failed to create command instance",
                command=command_name,
                error=str(e),
            )
            raise ValueError(error_msg) from e

        try:
            server_log.debug(
                "Calling command.call()",
                command=command_name,
                args=args,
                extra_args_keys=list(command_kwargs.keys()),
                verbosity=verbosity,
            )
            # Set verbosity context for the duration of command execution
            with verbosity_context(verbosity):
                result = command.call(*args, **command_kwargs)
            server_log.debug(
                "Command.call() returned",
                command=command_name,
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
                command=command_name,
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
                command=command_name,
                error=str(e),
            )


class RPCController(Controller):
    """JSON-RPC endpoint controller for CLI commands.

    Handles JSON-RPC requests from the Hop3 CLI, executing commands
    on the server with authentication and authorization checks.
    """

    path = "/rpc"

    @post("/", status_code=200)
    async def handle_rpc(self, request: Request, data: dict) -> Response:
        """Handle JSON-RPC request.

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

        command_name = cli_args[0]
        args = cli_args[1:]

        # Log all incoming RPC commands for debugging
        server_log.info(
            "RPC request received",
            command=command_name,
            args=args,
            extra_args_keys=list(extra_args.keys()),
            request_id=request_id,
        )

        # Look up command
        command_class = commands.get(command_name)

        # Check authentication (before revealing if command exists)
        auth_error = self._check_authentication(request, command_class)
        if auth_error:
            return auth_error

        # Validate command exists
        if command_class is None:
            return self._build_error_response(
                code=-32601,  # Method not found
                message=f"Command '{command_name}' not found",
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
        """Build a JSON-RPC error response.

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
        """Build a JSON-RPC success response.

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

    def _authenticate_from_bearer_token(self, request: Request) -> bool:
        """Try to authenticate using Bearer token from Authorization header.

        Args:
            request: HTTP request

        Returns:
            True if authentication succeeded, False otherwise
        """
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return False

        token = auth_header[7:].strip()
        token_info = validate_token(token)
        if not token_info:
            return False

        # Token is valid - set session data
        username = token_info["username"]
        request.session["user_id"] = username
        request.session["username"] = username
        request.session["scopes"] = token_info["scopes"]
        return True

    def _check_authentication(
        self, request: Request, command_class: type[Command] | None
    ) -> Response | None:
        """Check if the request is authenticated when required.

        For security, authentication is checked BEFORE revealing if the command
        exists. This prevents information disclosure about available commands.

        Args:
            request: HTTP request
            command_class: The command class (may be None if not found)

        Returns:
            Error response if authentication failed, None if OK
        """
        # Check session first
        user_id = request.session.get("user_id")
        if user_id:
            return None

        # Try Bearer token authentication (always try to extract user info)
        # This populates the session with username even if auth is not required
        token_valid = self._authenticate_from_bearer_token(request)

        # Skip authentication enforcement in unsafe testing mode
        if config.HOP3_UNSAFE:
            return None

        # Check if authentication is required
        if command_class is not None and not requires_authentication(command_class):
            return None

        # If token was valid, we're authenticated
        if token_valid:
            return None

        # Authentication failed
        return self._build_error_response(
            code=401,
            message="Authentication required. Use 'hop3 auth:login' to authenticate.",
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
        """Prepare command arguments by injecting username and token info.

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
            username = request.session.get("username")
            if username:
                prepared_args = (username, *prepared_args)

        # Pass token information to commands that need it (e.g., logout)
        if command_needs_token_info(command_class):
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                prepared_extra_args["_token"] = token

        return prepared_args, prepared_extra_args

    def _execute_command(
        self, command_name: str, args: tuple, extra_args: JsonDict, request_id: int
    ) -> Response:
        """Execute the command and return appropriate response.

        Args:
            command_name: Name of the command to execute
            args: Positional arguments
            extra_args: Keyword arguments
            request_id: Request ID for the response

        Returns:
            JSON-RPC response (success or error)
        """
        server_log.info(
            "Executing command",
            command=command_name,
            args=args,
            extra_args_keys=list(extra_args.keys()),
        )
        try:
            result = call(command_name, list(args), extra_args)
            server_log.info(
                "Command completed successfully",
                command=command_name,
                result_type=type(result).__name__,
                result_length=len(result) if isinstance(result, (list, dict)) else None,
            )
            return self._build_success_response(result, request_id)
        except ValueError as e:
            server_log.error(
                "Command failed with ValueError",
                command=command_name,
                error=str(e),
            )
            traceback.print_exc()
            return self._build_error_response(
                code=-32602,  # Invalid params
                message=str(e),
                request_id=request_id,
            )
        except RepositoryError as e:
            # Extract original exception details from advanced_alchemy wrapper
            error_msg = _extract_repository_error_message(e)
            server_log.error(
                "Command failed with RepositoryError",
                command=command_name,
                error=error_msg,
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
                command=command_name,
                error_type=type(e).__name__,
                error=str(e),
            )
            traceback.print_exc()
            return self._build_error_response(
                code=-32603,  # Internal error
                message=f"{type(e).__name__}: {e!s}",
                request_id=request_id,
            )


def _extract_repository_error_message(exc: RepositoryError) -> str:
    """Extract a meaningful error message from a RepositoryError.

    Advanced_alchemy wraps SQLAlchemy exceptions with generic messages like
    "There was an error during data processing". This function extracts the
    original exception details to provide better error messages.

    Args:
        exc: The RepositoryError exception

    Returns:
        A meaningful error message including original exception details
    """
    parts = []

    # Add the exception type
    parts.append(f"{type(exc).__name__}")

    # Try to get details from the wrapped exception's __cause__
    if exc.__cause__:
        cause = exc.__cause__
        cause_msg = str(cause)
        if cause_msg:
            parts.append(cause_msg)
    elif exc.detail and exc.detail not in {
        "There was an error during data processing",
        "An exception occurred",
    }:
        # Use the detail if it's not a generic message
        parts.append(exc.detail)
    else:
        # Fall back to str(exc) but skip generic messages
        exc_str = str(exc)
        if exc_str and exc_str not in {
            "There was an error during data processing",
            "An exception occurred",
        }:
            parts.append(exc_str)

    if len(parts) == 1:
        # Only have type name, add a generic but honest message
        parts.append("Database operation failed (no additional details available)")

    return ": ".join(parts)
