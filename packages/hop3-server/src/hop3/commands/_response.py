# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Response builder helpers for commands.

These helpers provide a clean, consistent way to build command responses.

Usage:
    from hop3.commands._response import text, error, success, warning, table, code

    return [
        text(f"App '{app_name}' deployed successfully"),
        table(headers=["Key", "Value"], rows=rows),
    ]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hop3.lib.console import CapturingConsole


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


def data(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Create a structured data response item.

    Used for returning JSON-serializable data that the CLI can process
    programmatically (e.g., for shell completion, JSON output mode).
    """
    return {"t": "data", "data": payload}


def blob(data_b64: str, filename: str = "") -> dict[str, Any]:
    """
    Create a binary-blob response item.

    Carries base64-encoded bytes the CLI writes verbatim to stdout (or a
    file). Used by ``addon <type> export`` to stream a dump to the client
    without a separate streaming channel — same base64-over-RPC approach the
    deploy upload uses, in reverse.
    """
    return {"t": "blob", "filename": filename, "data": data_b64}


def log_entry(msg: str, fg: str = "", level: int = 0) -> dict[str, Any]:
    """Create a log entry response item."""
    return {"t": "log", "msg": msg, "fg": fg, "level": level}


def stream(stream_id: str) -> dict[str, Any]:
    """Create a stream response item for SSE streaming."""
    return {"t": "stream", "stream_id": stream_id}


def hint(command: str, message: str) -> dict[str, Any]:
    """
    A follow-up-command suggestion the CLI renders in the user's own dialect.

    ``command`` is the bare verb path (e.g. ``"deploy"`` or ``"app restart"``)
    with NO target flags. The CLI prepends ``hop3 `` and appends the
    ``--context`` / ``--app`` selectors the user actually typed, then substitutes
    the result into ``message`` at the ``{cmd}`` placeholder.

    This keeps a suggested next step on the same context (server) the user is
    already targeting. A server-rendered string can't do this: ``--context`` is
    a CLI-local selector that never reaches the server, so a literal
    ``Run 'hop3 deploy'`` baked here would silently point at the *default*
    context — a different server.

    Example::

        return [
            text("Domains updated."),
            hint("deploy", "\\nNote: HOST_NAME changed. Run {cmd} to apply."),
        ]
    """
    return {"t": "hint", "command": command, "message": message}


def summary(message: str) -> dict[str, Any]:
    """
    Create a state-change summary item (ADR 036 D19c).

    Used by mutating commands to report what changed in one or two short
    lines. The CLI client renders summary items with a `[context / app]`
    prefix and routes them to stderr so they don't contaminate
    `hop3 cmd | grep` pipelines.

    Example::

        return [
            text("Configuration updated."),
            summary("set FOO=bar; restarted web worker."),
        ]
    """
    return {"t": "summary", "text": message}


def logs_to_response(logs: list[dict]) -> list[dict[str, Any]]:
    """
    Convert captured log entries to response format.

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


def build_log_response(
    captured: CapturingConsole, final_messages: list[str]
) -> list[dict[str, Any]]:
    """
    Build response from captured logs and final status messages.

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
