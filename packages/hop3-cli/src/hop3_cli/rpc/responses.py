# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""RPC response handling for the Hop3 CLI."""

from __future__ import annotations

import json
import re
import sys
from typing import TYPE_CHECKING, Any

from jsonrpcclient import Error, Ok

from hop3_cli.commands.help import (
    append_feedback_footer,
    append_local_commands_full_help,
    emit_status_line,
    inject_local_commands_into_help,
    is_help_command,
)
from hop3_cli.commands.local.completion_cmd import read_apps_cache
from hop3_cli.core.suggest import (
    closest_matches,
    colon_to_space_suggestion,
    format_did_you_mean,
    load_cached_commands,
)
from hop3_cli.exceptions import DeploymentError
from hop3_cli.exit_codes import (
    HTTP_PAYLOAD_TOO_LARGE,
    ExitCode,
    map_message_to_exit,
    map_rpc_code_to_exit,
)
from hop3_cli.rpc.client import resolve_ssl_verification
from hop3_cli.ui.console import err

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_response(
    response: Any,
    cli_args: list[str],
    config: Config,
    printer: RichPrinter,
    *,
    tunnel_port: int | None = None,
) -> None:
    """
    Handle the RPC response.

    Args:
        response: The JSON-RPC response
        cli_args: Original CLI arguments
        config: CLI configuration
        printer: Output printer
        tunnel_port: Local SSH tunnel port if using SSH tunnel (for streaming)
    """
    match response:
        case Ok(result=result):
            handle_ok_response(
                result, cli_args, config, printer, tunnel_port=tunnel_port
            )
        case Error(code=code, message=message):
            handle_error_response(code, message, printer)
        case None:
            pass

    # Flush JSON output if in JSON mode
    if printer.json_output:
        printer.flush_json()


def handle_ok_response(
    result: list[dict],
    cli_args: list[str],
    config: Config,
    printer: RichPrinter,
    *,
    tunnel_port: int | None = None,
) -> None:
    """
    Handle successful RPC response.

    Args:
        result: The result payload
        cli_args: Original CLI arguments
        config: CLI configuration
        printer: Output printer
        tunnel_port: Local SSH tunnel port if using SSH tunnel (for streaming)
    """
    if cli_args[:2] == ["addon", "exists"]:
        _handle_predicate_response(result, printer)
    elif is_help_command(cli_args) and not printer.json_output:
        # ADR 036 D11: bare `hop3 help` gets local commands injected, then the
        # feedback-link footer (G7), and a dynamic context/app status line
        # emitted separately to stderr (D19).
        #
        # `hop3 help --all -v` is the full-document variant: the server already
        # rendered the full help for every server command, so instead of
        # injecting local one-liners we append the *full* help for local
        # commands, keeping the document a complete reference.
        if printer.verbose and cli_args == ["help", "--all"]:
            result = append_local_commands_full_help(result)
        else:
            result = inject_local_commands_into_help(result)
        result = append_feedback_footer(result)
        printer.print(result)
        emit_status_line(config)
    elif _is_streaming_response(result):
        # Handle streaming response (real-time deployment logs)
        _handle_streaming_response(result, config, printer, tunnel_port=tunnel_port)
    else:
        printer.print(result)


def _handle_predicate_response(result: list[dict], printer: RichPrinter) -> None:
    """
    Turn an ``addon exists`` data result into a Unix predicate.

    Silent, exit 0 (exists) / 1 (absent), so it composes with shell ``&&``/
    ``||``. Under ``--json`` the ``{"exists": ...}`` payload is still emitted.
    Anything unexpected (e.g. a usage error item) is shown and exits 2.
    """
    payload: dict | None = None
    for item in result or []:
        if item.get("t") == "data" and isinstance(item.get("data"), dict):
            payload = item["data"]
            break

    if payload is not None and "exists" in payload:
        if printer.json_output:
            printer.print([{"t": "data", "data": payload}])
            printer.flush_json()
        sys.exit(ExitCode.SUCCESS if payload["exists"] else 1)

    # No predicate payload (usage error, etc.): surface it and fail non-zero.
    printer.print(result)
    if printer.json_output:
        printer.flush_json()
    sys.exit(ExitCode.USAGE_ERROR)


def _is_streaming_response(result: list[dict]) -> bool:
    """Check if the response is a streaming response."""
    return (
        len(result) == 1 and result[0].get("t") == "stream" and "stream_id" in result[0]
    )


def _handle_streaming_response(
    result: list[dict],
    config: Config,
    printer: RichPrinter,
    *,
    tunnel_port: int | None = None,
) -> None:
    """
    Handle streaming response by connecting to SSE endpoint.

    Args:
        result: RPC response containing stream_id
        config: CLI configuration
        printer: Printer for output
        tunnel_port: Local SSH tunnel port if using SSH tunnel
    """
    # Imported lazily so tests can patch ``stream_deployment_logs`` at its source
    # module (the call binds late, not at import time).
    from hop3_cli.rpc.streaming import (  # ruff:ignore[import-outside-top-level]
        stream_deployment_logs,
    )

    stream_id: str | None = result[0].get("stream_id")
    if not stream_id:
        printer.print([
            {"t": "error", "text": "Invalid streaming response: no stream_id"}
        ])
        sys.exit(1)

    # Get API URL from config. Must use get_api_url() (context-aware, matching
    # how Client resolves the connection) — NOT the flat config.get("api_url"),
    # which ADR 042 stopped populating once the URL moved into [contexts.*].
    # The flat lookup returned "" for context-configured CLIs, so streaming
    # deploys aborted with "No API URL configured" even though the RPC itself
    # had just connected fine.
    api_url: str = config.get_api_url() or ""
    if not api_url:
        printer.print([{"t": "error", "text": "No API URL configured"}])
        sys.exit(1)

    # Determine the base URL for streaming
    base_url: str
    verify_ssl: bool | str
    if tunnel_port is not None:
        # SSH tunnel mode: use localhost with the forwarded port
        base_url = f"http://localhost:{tunnel_port}"
        # No SSL verification needed for localhost tunnel
        verify_ssl = False
    elif api_url.startswith("ssh://"):
        # SSH URL but no tunnel port passed - this shouldn't happen
        # Fall back to warning (defensive coding)
        printer.print([
            {
                "t": "warning",
                "text": "SSH tunnel port not available for streaming. Waiting for deployment to complete...",
            }
        ])
        return
    else:
        # Direct HTTP/HTTPS connection. Resolve TLS the SAME way the RPC client
        # does (honor a pinned ssl_cert; parse a string verify_ssl) so the
        # stream doesn't fail the deploy report on a deploy that succeeded over
        # /rpc (audit 2026-06 B1).
        base_url = api_url
        verify_ssl = resolve_ssl_verification(api_url, config)

    # Get token for authentication
    token: str | None = config.get_api_token()

    # Connect to stream and display logs
    try:
        stream_deployment_logs(
            base_url=base_url,
            stream_id=stream_id,
            printer=printer,
            token=token,
            verify_ssl=verify_ssl,
        )
    except DeploymentError:
        sys.exit(1)


def handle_error_response(
    code: int, message: str, printer: RichPrinter | None = None
) -> None:
    """
    Handle RPC error response.

    Args:
        code: The JSON-RPC or HTTP error code
        message: The error message
        printer: Optional RichPrinter for JSON output mode
    """
    clean_message = message
    logs_to_display = None

    # Check for embedded logs in error message (format: LOGS:<json>|||<error>)
    if clean_message.startswith("LOGS:") and "|||" in clean_message:
        try:
            logs_part, error_part = clean_message[5:].split("|||", 1)
            logs_to_display = json.loads(logs_part)
            clean_message = error_part
        except (json.JSONDecodeError, ValueError):
            # If parsing fails, treat as normal error message
            pass

    prefixes_to_strip = [
        "Command execution failed: ",
        "Deployment failed: ",
    ]
    for prefix in prefixes_to_strip:
        clean_message = clean_message.removeprefix(prefix)

    # Add helpful hints for specific error codes (ADR 036 D10 — did-you-mean).
    if code == HTTP_PAYLOAD_TOO_LARGE:  # 413 — deploy archive too big
        clean_message = _payload_too_large_message()
    elif code == -32601:  # Method/command not found
        suggestion = _command_not_found_suggestion(clean_message)
        if suggestion:
            clean_message += f"\n\n{suggestion}"
        clean_message += "\n\nRun 'hop help' to see available commands."
    else:
        # ADR 036 M8.3: for "app 'foo' not found" errors, offer a closest-match
        # suggestion against the cached app list. Silent when the cache is
        # empty (the user just hasn't run `hop3 completion --refresh` yet).
        app_suggestion = _app_not_found_suggestion(clean_message)
        if app_suggestion:
            clean_message += f"\n\n{app_suggestion}"

    # Determine exit code from RPC code, falling back to message analysis
    exit_code = map_rpc_code_to_exit(code)
    if exit_code == ExitCode.GENERAL_ERROR:
        # Try to infer from message content
        exit_code = map_message_to_exit(clean_message)

    # Display logs first if we have them (so user sees deployment progress)
    if logs_to_display and printer:
        printer.print(logs_to_display)

    # Output error in appropriate format
    if printer and printer.json_output:
        error_obj = {
            "success": False,
            "error": {
                "code": code,
                "message": clean_message,
                "exit_code": exit_code,
            },
        }
        print(json.dumps(error_obj, indent=2))
    else:
        err(clean_message)

    sys.exit(exit_code)


def _payload_too_large_message() -> str:
    """Actionable diagnostic for an HTTP 413 on deploy (archive too large)."""
    return (
        "Deploy archive rejected by the server: it's too large (HTTP 413).\n"
        "\n"
        "Run 'hop3 deploy --dry-run' to see exactly what's in the archive\n"
        "(total size and the largest files/directories).\n"
        "\n"
        "The server's default upload limit is 200 MB. To shrink the archive:\n"
        "  - Exclude large directories via [build].ignore in hop3.toml\n"
        "    (e.g. data/, media/, uploads/, build output, large assets).\n"
        "  - .git/, node_modules/, .venv/ are already excluded by default.\n"
        "\n"
        "If the archive is legitimately large, ask your server admin to raise\n"
        "request_max_body_size (Litestar) and client_max_body_size (nginx)."
    )


def _command_not_found_suggestion(error_message: str) -> str | None:
    """
    Build a 'Did you mean...?' suggestion for an unknown-command error.

    The server's error message looks like ``"Command 'foo bar' not found"``.
    We extract the typed command name and offer two kinds of suggestion
    (ADR 036 D10):

    1. **Colon -> space migration hint** (M5.4): if the user typed
       ``foo:bar``, point them at ``foo bar`` with a one-line note that the
       syntax changed. Many users still have ADR-pre-D1 muscle memory.
    2. **Closest-match suggestions** (M5.2): otherwise, consult the cached
       command list (written by ``hop3 completion --refresh``) and propose
       the closest matches by edit distance.

    Returns ``None`` if no useful suggestion could be made.
    """
    typed = _extract_typed_command(error_message)
    if not typed:
        return None

    # Migration hint: ``foo:bar`` -> ``foo bar``.
    space_form = colon_to_space_suggestion(typed)
    if space_form is not None:
        return (
            f"The syntax changed in v0.5: command names use spaces, not colons.\n"
            f"Try: hop3 {space_form}"
        )

    # Closest match against the cached command list.
    candidates = load_cached_commands()
    if not candidates:
        return None
    matches = closest_matches(typed, candidates)
    return format_did_you_mean(typed, matches)


_APP_NOT_FOUND_RE = re.compile(r"[Aa]pp ['\"]([^'\"]+)['\"] not found")


def _app_not_found_suggestion(error_message: str) -> str | None:
    """
    Return a 'Did you mean...?' hint for app-not-found errors.

    Looks for the ``App 'foo' not found`` pattern and consults the local
    app-name cache populated by ``hop3 completion --refresh``. Returns
    None if the pattern isn't present or the cache is empty.
    """
    match = _APP_NOT_FOUND_RE.search(error_message)
    if not match:
        return None
    typed = match.group(1)

    candidates = read_apps_cache()
    if not candidates:
        return None
    matches = closest_matches(typed, candidates)
    return format_did_you_mean(typed, matches)


def _extract_typed_command(error_message: str) -> str | None:
    """
    Pull the typed command path out of a server "not found" message.

    The server formats unknown-command errors as
    ``"Command 'foo bar' not found"`` (see ``rpc.py``). Anything outside that
    pattern returns None — we only want to suggest when we know what the user
    typed.
    """
    # Find the first single-quoted span; if present, that's the command name.
    start = error_message.find("'")
    if start == -1:
        return None
    end = error_message.find("'", start + 1)
    if end == -1:
        return None
    return error_message[start + 1 : end]
