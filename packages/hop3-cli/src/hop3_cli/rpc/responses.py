# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""RPC response handling for the Hop3 CLI."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from jsonrpcclient import Error, Ok

from hop3_cli.commands.help import inject_local_commands_into_help, is_help_command
from hop3_cli.exit_codes import ExitCode, map_message_to_exit, map_rpc_code_to_exit
from hop3_cli.tokens import JWT_PATTERN
from hop3_cli.ui.console import err

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_response(
    response: Any, cli_args: list[str], config: Config, printer: RichPrinter
) -> None:
    """Handle the RPC response."""

    match response:
        case Ok(result=result):
            handle_ok_response(result, cli_args, config, printer)
        case Error(code=code, message=message):
            handle_error_response(code, message, printer)
        case None:
            pass

    # Flush JSON output if in JSON mode
    if printer.json_output:
        printer.flush_json()


def handle_ok_response(
    result: list[dict], cli_args: list[str], config: Config, printer: RichPrinter
) -> None:
    """Handle successful RPC response."""
    if cli_args and cli_args[0] == "auth:login":
        handle_login_response(result, config, printer)
    elif is_help_command(cli_args) and not printer.json_output:
        result = inject_local_commands_into_help(result)
        printer.print(result)
    elif _is_streaming_response(result):
        # Handle streaming response (real-time deployment logs)
        _handle_streaming_response(result, config, printer)
    else:
        printer.print(result)


def _is_streaming_response(result: list[dict]) -> bool:
    """Check if the response is a streaming response."""
    return (
        result
        and len(result) == 1
        and result[0].get("t") == "stream"
        and "stream_id" in result[0]
    )


def _handle_streaming_response(
    result: list[dict], config: Config, printer: RichPrinter
) -> None:
    """Handle streaming response by connecting to SSE endpoint.

    Args:
        result: RPC response containing stream_id
        config: CLI configuration
        printer: Printer for output
    """
    from hop3_cli.rpc.streaming import stream_deployment_logs  # noqa: PLC0415

    stream_id = result[0].get("stream_id")
    if not stream_id:
        printer.print([{"t": "error", "text": "Invalid streaming response: no stream_id"}])
        sys.exit(1)

    # Get API URL from config
    api_url = config.get("api_url", "")
    if not api_url:
        printer.print([{"t": "error", "text": "No API URL configured"}])
        sys.exit(1)

    # Handle SSH tunnel URLs - need to use the forwarded HTTP URL
    if api_url.startswith("ssh://"):
        # When using SSH tunnel, the actual HTTP connection goes to localhost
        # The tunnel is already established by the RPC client
        # We need to get the local forwarded port
        # For now, fall back to non-streaming behavior
        printer.print([{
            "t": "warning",
            "text": "Streaming not yet supported over SSH tunnel. Waiting for deployment to complete...",
        }])
        # TODO: Implement SSH tunnel support for streaming
        # The RPC client establishes the tunnel, we need to reuse it
        return

    # Get token for authentication
    token = config.get("api_token")

    # Check SSL verification setting
    verify_ssl = config.get("verify_ssl", True)

    # Connect to stream and display logs
    success = stream_deployment_logs(
        base_url=api_url,
        stream_id=stream_id,
        printer=printer,
        token=token,
        verify_ssl=verify_ssl,
    )

    if not success:
        sys.exit(1)


def handle_error_response(
    code: int, message: str, printer: RichPrinter | None = None
) -> None:
    """Handle RPC error response.

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

    # Add helpful hints for specific error codes
    if code == -32601:  # Method/command not found
        clean_message += "\n\nRun 'hop help' to see available commands."

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


def handle_login_response(
    result: list[dict], config: Config, printer: RichPrinter
) -> None:
    """Handle auth:login response - extract and save token, then print modified output.

    Args:
        result: The RPC response from auth:login
        config: The config object to save the token to
        printer: Printer for output
    """
    token = None
    modified_result = []
    found_token = False

    # Keywords that indicate manual token save instructions
    skip_keywords = [
        "your api token",
        "save this token",
        "config file",
        "api_token =",
        "environment variable",
        "export hop3_api_token",
    ]

    for item in result:
        if item.get("t") == "text":
            text = item.get("text", "")

            # Check if this text contains a JWT token
            match = JWT_PATTERN.search(text)
            if match and not found_token:
                token = match.group(0)
                found_token = True
                # Skip the line containing the JWT token itself
                continue

            # Skip all manual instruction messages (before or after token)
            if any(keyword in text.lower() for keyword in skip_keywords):
                continue

            # Skip empty or whitespace-only text
            if not text.strip():
                continue

            # Keep other text messages (success message, etc.)
            modified_result.append(item)
        else:
            # Keep non-text messages (tables, errors, etc.)
            modified_result.append(item)

    # Save token if found
    if token:
        try:
            config.save({"api_token": token})
            # Add success message about saving the token
            modified_result.append({
                "t": "text",
                "text": f"\nAPI token saved to {config.config_file}",
            })
            modified_result.append({
                "t": "text",
                "text": "You can now use hop3 commands without additional authentication.",
            })
        except Exception as e:
            modified_result.append({
                "t": "error",
                "text": f"Failed to save token to config: {e}",
            })
            modified_result.append({
                "t": "text",
                "text": f"\nYour API token: {token}",
            })
            modified_result.append({
                "t": "text",
                "text": f"Please save it manually to {config.config_file or '~/.config/hop3-cli/config.toml'}",
            })

    # Print the modified result
    printer.print(modified_result)
