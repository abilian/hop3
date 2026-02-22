# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Response builder helpers for commands.

These helpers provide a clean, consistent way to build command responses.

Usage:
    from hop3.commands._response import text, error, success, warning, table, code

    return [
        text(f"App '{app_name}' deployed successfully"),
        table(headers=["Key", "Value"], rows=rows),
    ]
"""

from __future__ import annotations

from typing import Any


def text(message: str) -> dict[str, Any]:
    """Create a text response item."""
    return {"t": "text", "text": message}


def error(message: str) -> dict[str, Any]:
    """Create an error response item."""
    return {"t": "error", "text": message}


def success(message: str) -> dict[str, Any]:
    """Create a success response item."""
    return {"t": "success", "text": message}


def warning(message: str) -> dict[str, Any]:
    """Create a warning response item."""
    return {"t": "warning", "text": message}


def table(
    headers: list[str],
    rows: list[list[Any]],
) -> dict[str, Any]:
    """Create a table response item."""
    return {"t": "table", "headers": headers, "rows": rows}


def code(content: str, lang: str = "") -> dict[str, Any]:
    """Create a code block response item."""
    return {"t": "code", "lang": lang, "text": content}
