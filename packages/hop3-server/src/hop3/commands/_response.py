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


def log_entry(msg: str, fg: str = "", level: int = 0) -> dict[str, Any]:
    """Create a log entry response item."""
    return {"t": "log", "msg": msg, "fg": fg, "level": level}


def logs_to_response(logs: list[dict]) -> list[dict[str, Any]]:
    """Convert captured log entries to response format.

    Args:
        logs: List of log entries from captured.get_logs()

    Returns:
        Response list with log entries in RPC response format
    """
    return [
        log_entry(
            msg=entry["msg"],
            fg=entry.get("fg", ""),
            level=entry.get("level", 0),
        )
        for entry in logs
    ]


def build_log_response(captured, final_messages: list[str]) -> list[dict[str, Any]]:
    """Build response from captured logs and final status messages.

    Args:
        captured: CapturedLogs context manager result
        final_messages: List of final text messages to append

    Returns:
        Response list with log entries and text messages
    """
    response = logs_to_response(captured.get_logs())
    for msg in final_messages:
        response.append(text(msg))
    return response
