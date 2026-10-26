# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
What a JSON-RPC error from hop3-server says, read as data.

Shared by the CLI and the TUI, which each extracted ``error.message`` on their
own; and the CLI told a plain "sign in" 401 from a deleted or disabled account
by the prefix of the server's prose. The server now names the case in
``error.data.kind``.
"""

from __future__ import annotations

#: ``error.data.kind`` of a 401: no valid credential was presented.
UNAUTHENTICATED = "unauthenticated"
#: ``error.data.kind`` of a 401: the token names an account that is deleted or
#: disabled, which the message explains.
ACCOUNT_UNUSABLE = "account_unusable"


def server_error(body: object) -> tuple[str, str]:
    """``(message, kind)`` of a JSON-RPC error body; empty strings when absent."""
    if not isinstance(body, dict):
        return "", ""
    error = body.get("error")
    if not isinstance(error, dict):
        return "", ""
    message = error.get("message")
    data = error.get("data")
    kind = data.get("kind") if isinstance(data, dict) else None
    return (
        message if isinstance(message, str) else "",
        kind if isinstance(kind, str) else "",
    )


#: ``error.data.kind`` of a change to a protected server that nothing named
#: (ADR 042, rule D): a checkout's binding or the global context chose it.
PROTECTED_NEEDS_EXPLICIT = "protected_needs_explicit_target"
#: ``error.data.kind`` of a change to a protected server that waits for the
#: operator to type the app's name.
PROTECTED_NEEDS_CONFIRMATION = "protected_needs_confirmation"
