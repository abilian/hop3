# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""JSON-RPC communication layer for the Hop3 CLI.

This package handles all communication with the Hop3 server:
- client: RPC client with SSH tunnel support
- tunnel: SSH tunnel implementation (reference, uses sshtunnel package)
- responses: Response parsing and handling
"""

from __future__ import annotations

from .client import Client
from .responses import (
    handle_error_response,
    handle_login_response,
    handle_ok_response,
    handle_response,
)

__all__ = [
    "Client",
    "handle_error_response",
    "handle_login_response",
    "handle_ok_response",
    "handle_response",
]
