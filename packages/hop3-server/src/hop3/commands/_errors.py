# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Generic error handling for CLI commands.

This module provides a reusable mechanism for handling exceptions in commands,
converting them to user-friendly error messages while logging detailed info
for debugging.

Usage:
    from hop3.commands._errors import command_context

    class MyCmd(Command):
        def call(self, *args, **kwargs):
            with command_context("deploying app", app_name=app_name):
                do_something_risky()

    # Or with custom error handlers:
    with command_context("building image") as ctx:
        ctx.on_error(subprocess.CalledProcessError, handler=format_subprocess_error)
        run_build()
"""

from __future__ import annotations

import subprocess
import sys
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator


@dataclass
class CommandError(Exception):
    """Structured error from a command.

    Attributes:
        message: User-friendly error message
        details: Additional details (shown in verbose mode)
        cause: Original exception that caused this error
    """

    message: str
    details: str | None = None
    cause: Exception | None = None

    def __str__(self) -> str:
        return self.message


@dataclass
class ErrorContext:
    """Context for error handling within a command."""

    operation: str
    context_vars: dict[str, Any] = field(default_factory=dict)
    _handlers: dict[type, Callable] = field(default_factory=dict)

    def on_error(
        self, exc_type: type[Exception], handler: Callable[[Exception], str]
    ) -> None:
        """Register a custom handler for a specific exception type.

        Args:
            exc_type: Exception class to handle
            handler: Function that takes the exception and returns error message
        """
        self._handlers[exc_type] = handler

    def format_error(self, exc: Exception) -> str:
        """Format an exception into a user-friendly message.

        Args:
            exc: The exception to format

        Returns:
            User-friendly error message
        """
        # Check for custom handler
        for exc_type, handler in self._handlers.items():
            if isinstance(exc, exc_type):
                return handler(exc)

        # Default formatting by exception type
        if isinstance(exc, subprocess.CalledProcessError):
            return _format_subprocess_error(exc)

        if isinstance(exc, FileNotFoundError):
            return f"File not found: {exc.filename}"

        if isinstance(exc, PermissionError):
            return f"Permission denied: {exc.filename if hasattr(exc, 'filename') else exc}"

        if isinstance(exc, TimeoutError):
            return "Operation timed out"

        # Generic fallback
        return f"{self.operation} failed: {exc}"


def _format_subprocess_error(exc: subprocess.CalledProcessError) -> str:
    """Format a subprocess error with command output.

    Args:
        exc: CalledProcessError exception

    Returns:
        Formatted error message with stdout/stderr
    """
    parts = [
        f"Command exited with code {exc.returncode}",
        f"Command: {exc.cmd}",
    ]
    if exc.stdout:
        stdout = exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode()
        parts.append(f"\nStdout:\n{stdout}")
    if exc.stderr:
        stderr = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode()
        parts.append(f"\nStderr:\n{stderr}")

    return "\n".join(parts)


def _log_error(operation: str, exc: Exception, context_vars: dict[str, Any]) -> None:
    """Log error details to stderr for server-side debugging.

    Args:
        operation: Description of what was happening
        exc: The exception that occurred
        context_vars: Contextual variables (app_name, etc.)
    """
    context_str = ", ".join(f"{k}={v}" for k, v in context_vars.items())
    print(f"[ERROR] {operation} failed ({context_str}):", file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)


@contextmanager
def command_context(
    operation: str, **context_vars: Any
) -> Generator[ErrorContext, None, None]:
    """Context manager for command error handling.

    Catches exceptions, logs them for debugging, and re-raises as ValueError
    with a user-friendly message for the RPC handler.

    Args:
        operation: Description of the operation (e.g., "deploying app")
        **context_vars: Contextual variables for logging (e.g., app_name="myapp")

    Yields:
        ErrorContext for registering custom handlers

    Raises:
        ValueError: Re-raised with user-friendly message on any exception

    Example:
        with command_context("deploying app", app_name="myapp") as ctx:
            ctx.on_error(DockerError, lambda e: f"Docker failed: {e.reason}")
            do_deploy(app)
    """
    ctx = ErrorContext(operation=operation, context_vars=context_vars)
    try:
        yield ctx
    except ValueError:
        # ValueError is already our error format, just re-raise
        raise
    except CommandError as e:
        # CommandError is already structured, log and convert to ValueError
        _log_error(operation, e, context_vars)
        raise ValueError(e.message) from e
    except Exception as e:
        # Log detailed error for debugging
        _log_error(operation, e, context_vars)
        # Convert to user-friendly message
        error_msg = ctx.format_error(e)
        raise ValueError(error_msg) from e


# Convenience function for simple cases without custom handlers
def handle_command_error(operation: str, **context_vars: Any):
    """Decorator version of command_context for simple cases.

    Usage:
        @handle_command_error("deploying app")
        def call(self, *args, **kwargs):
            ...
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            with command_context(operation, **context_vars):
                return func(*args, **kwargs)

        return wrapper

    return decorator
