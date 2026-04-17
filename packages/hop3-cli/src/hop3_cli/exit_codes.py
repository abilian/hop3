# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Exit codes for the Hop3 CLI (ADR 036 D16).

The numbers below come from ADR 036 D16. Scripts can distinguish
user error (2, 10), resolution (3), auth (4, 5), server (7), and
deployment (8). The JSON envelope includes ``error.exit_code`` so
JSON consumers don't have to map error strings.

Reserved values:
    0   Success (including empty results)
    1   Generic error (fallback)
    2   Usage / syntax error (validation, malformed args)
    3   Resolution error (app / context / target not found)
    4   Authentication error (not logged in, token expired)
    5   Authorization error (forbidden)
    6   Conflict (already exists, locked, in use)
    7   Network / server error (connection, timeout, 5xx)
    8   Deployment failure
    9   Plugin error
    10  Confirmation declined or non-tty blocked
    130 Interrupted (SIGINT)
"""

from __future__ import annotations


class ExitCode:
    """Exit code constants per ADR 036 D16."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    USAGE_ERROR = 2
    RESOLUTION_ERROR = 3
    AUTH_ERROR = 4
    AUTHZ_ERROR = 5
    CONFLICT_ERROR = 6
    NETWORK_ERROR = 7
    DEPLOYMENT_ERROR = 8
    PLUGIN_ERROR = 9
    CONFIRMATION_DECLINED = 10
    INTERRUPTED = 130

    # Back-compat names from the pre-D16 layout. New code should use the
    # D16-aligned names above. These aliases let older call sites keep
    # working while the sweep finishes.
    NOT_FOUND = RESOLUTION_ERROR
    VALIDATION_ERROR = USAGE_ERROR
    SERVER_ERROR = NETWORK_ERROR
    CONNECTION_ERROR = NETWORK_ERROR
    TIMEOUT_ERROR = NETWORK_ERROR


# JSON-RPC error codes
RPC_METHOD_NOT_FOUND = -32601
RPC_INVALID_PARAMS = -32602
RPC_INTERNAL_ERROR = -32603

# HTTP status codes
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_SERVER_ERROR = 500


def map_rpc_code_to_exit(code: int) -> int:
    """Map a JSON-RPC or HTTP error code to an ADR 036 D16 exit code.

    Args:
        code: The error code from JSON-RPC response or HTTP status

    Returns:
        Appropriate exit code from ExitCode class
    """
    mapping = {
        # HTTP status codes
        HTTP_UNAUTHORIZED: ExitCode.AUTH_ERROR,
        HTTP_FORBIDDEN: ExitCode.AUTHZ_ERROR,
        HTTP_NOT_FOUND: ExitCode.RESOLUTION_ERROR,
        HTTP_CONFLICT: ExitCode.CONFLICT_ERROR,
        HTTP_SERVER_ERROR: ExitCode.NETWORK_ERROR,
        # JSON-RPC error codes
        RPC_METHOD_NOT_FOUND: ExitCode.RESOLUTION_ERROR,
        RPC_INVALID_PARAMS: ExitCode.USAGE_ERROR,
        RPC_INTERNAL_ERROR: ExitCode.NETWORK_ERROR,
    }
    return mapping.get(code, ExitCode.GENERAL_ERROR)


def map_message_to_exit(message: str) -> int:
    """Map an error message to an ADR 036 D16 exit code based on content.

    Used as a fallback when the error code doesn't carry enough context
    (e.g., generic server error wrapping a domain-specific failure).

    Args:
        message: The error message text

    Returns:
        Appropriate exit code from ExitCode class
    """
    message_lower = message.lower()

    if "not found" in message_lower or "does not exist" in message_lower:
        return ExitCode.RESOLUTION_ERROR

    if "forbidden" in message_lower or "permission denied" in message_lower:
        return ExitCode.AUTHZ_ERROR

    if "unauthorized" in message_lower or "authentication" in message_lower:
        return ExitCode.AUTH_ERROR

    if "already exists" in message_lower or "conflict" in message_lower:
        return ExitCode.CONFLICT_ERROR

    if "deployment failed" in message_lower or "deploy failed" in message_lower:
        return ExitCode.DEPLOYMENT_ERROR

    if (
        "timeout" in message_lower
        or "timed out" in message_lower
        or (
            "connection" in message_lower
            and ("refused" in message_lower or "failed" in message_lower)
        )
    ):
        return ExitCode.NETWORK_ERROR

    if (
        "invalid" in message_lower
        or "validation" in message_lower
        or "usage:" in message_lower
    ):
        return ExitCode.USAGE_ERROR

    return ExitCode.GENERAL_ERROR
