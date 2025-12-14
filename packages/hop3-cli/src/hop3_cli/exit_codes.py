# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Exit codes for the Hop3 CLI.

These exit codes allow automation tools to distinguish between different
types of failures without parsing error messages.

Exit Code Reference:
    0 - Success
    1 - General/unknown error (fallback)
    2 - Authentication error (invalid token, 401)
    3 - Not found (command not found, app not found, -32601)
    4 - Validation error (invalid parameters, -32602)
    5 - Server error (internal server error, -32603, 500)
    6 - Connection error (connection refused, SSL error)
    7 - Timeout error
"""

from __future__ import annotations


class ExitCode:
    """Exit code constants for CLI operations."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    AUTH_ERROR = 2
    NOT_FOUND = 3
    VALIDATION_ERROR = 4
    SERVER_ERROR = 5
    CONNECTION_ERROR = 6
    TIMEOUT_ERROR = 7


# JSON-RPC error codes
RPC_METHOD_NOT_FOUND = -32601
RPC_INVALID_PARAMS = -32602
RPC_INTERNAL_ERROR = -32603

# HTTP status codes
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR = 500


def map_rpc_code_to_exit(code: int) -> int:
    """Map a JSON-RPC or HTTP error code to a CLI exit code.

    Args:
        code: The error code from JSON-RPC response or HTTP status

    Returns:
        Appropriate exit code from ExitCode class
    """
    mapping = {
        # HTTP status codes
        HTTP_UNAUTHORIZED: ExitCode.AUTH_ERROR,
        HTTP_NOT_FOUND: ExitCode.NOT_FOUND,
        HTTP_SERVER_ERROR: ExitCode.SERVER_ERROR,
        # JSON-RPC error codes
        RPC_METHOD_NOT_FOUND: ExitCode.NOT_FOUND,
        RPC_INVALID_PARAMS: ExitCode.VALIDATION_ERROR,
        RPC_INTERNAL_ERROR: ExitCode.SERVER_ERROR,
    }
    return mapping.get(code, ExitCode.GENERAL_ERROR)


def map_message_to_exit(message: str) -> int:
    """Map an error message to a CLI exit code based on content.

    This is used as a fallback when the error code doesn't provide
    enough context (e.g., general server errors with specific messages).

    Args:
        message: The error message text

    Returns:
        Appropriate exit code from ExitCode class
    """
    message_lower = message.lower()

    # Check for specific error patterns
    if "not found" in message_lower or "does not exist" in message_lower:
        return ExitCode.NOT_FOUND

    if "unauthorized" in message_lower or "authentication" in message_lower:
        return ExitCode.AUTH_ERROR

    if "timeout" in message_lower or "timed out" in message_lower:
        return ExitCode.TIMEOUT_ERROR

    if "connection" in message_lower and (
        "refused" in message_lower or "failed" in message_lower
    ):
        return ExitCode.CONNECTION_ERROR

    if "invalid" in message_lower or "validation" in message_lower:
        return ExitCode.VALIDATION_ERROR

    return ExitCode.GENERAL_ERROR
