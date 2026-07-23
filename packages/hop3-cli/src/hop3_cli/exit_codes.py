# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Exit codes for the Hop3 CLI (ADR 036 D16).

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


# JSON-RPC error codes
RPC_METHOD_NOT_FOUND = -32601
RPC_INVALID_PARAMS = -32602
RPC_INTERNAL_ERROR = -32603

# HTTP status codes
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_PAYLOAD_TOO_LARGE = 413
HTTP_SERVER_ERROR = 500


def map_rpc_code_to_exit(code: int) -> int:
    """
    Map a JSON-RPC or HTTP error code to an ADR 036 D16 exit code.

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
        HTTP_PAYLOAD_TOO_LARGE: ExitCode.USAGE_ERROR,
        HTTP_SERVER_ERROR: ExitCode.NETWORK_ERROR,
        # JSON-RPC error codes
        RPC_METHOD_NOT_FOUND: ExitCode.RESOLUTION_ERROR,
        RPC_INVALID_PARAMS: ExitCode.USAGE_ERROR,
        RPC_INTERNAL_ERROR: ExitCode.NETWORK_ERROR,
    }
    return mapping.get(code, ExitCode.GENERAL_ERROR)


# Ordered table mapping (any-substring-match) → ExitCode. First match wins, so
# more specific patterns must come before more general ones. The network case
# carries a small predicate because "connection failed/refused" must match
# only when the word "connection" is also present (a bare "failed" is too
# generic).
_MESSAGE_PATTERNS: list[tuple[tuple[str, ...], int]] = [
    (("not found", "does not exist"), ExitCode.RESOLUTION_ERROR),
    (("forbidden", "permission denied"), ExitCode.AUTHZ_ERROR),
    (("unauthorized", "authentication"), ExitCode.AUTH_ERROR),
    (("already exists", "conflict"), ExitCode.CONFLICT_ERROR),
    (("deployment failed", "deploy failed"), ExitCode.DEPLOYMENT_ERROR),
    (("timeout", "timed out"), ExitCode.NETWORK_ERROR),
    (("invalid", "validation", "usage:"), ExitCode.USAGE_ERROR),
]


def map_message_to_exit(message: str) -> int:
    """
    Map an error message to an ADR 036 D16 exit code based on content.

    Used as a fallback when the error code doesn't carry enough context
    (e.g., generic server error wrapping a domain-specific failure).
    """
    msg = message.lower()

    # "connection refused/failed" only counts as a NETWORK_ERROR when the
    # word "connection" co-occurs — handled out-of-table because of the
    # conjunction.
    if "connection" in msg and ("refused" in msg or "failed" in msg):
        return ExitCode.NETWORK_ERROR

    for patterns, code in _MESSAGE_PATTERNS:
        if any(p in msg for p in patterns):
            return code

    return ExitCode.GENERAL_ERROR
