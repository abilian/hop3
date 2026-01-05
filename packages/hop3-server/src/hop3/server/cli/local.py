# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Local command execution for hop3-server.

This command allows executing RPC commands directly on the server without going through
the network layer. Useful for server administration and debugging.

Example:
    hop3-server local apps
    hop3-server local auth:whoami testuser
    hop3-server local config:set myapp KEY=value
"""

from __future__ import annotations

import json
import sys
import traceback
from argparse import ArgumentParser

from hop3.commands import Command as RpcCommand
from hop3.lib.registry import lookup, register
from hop3.lib.scanner import scan_package
from hop3.orm import get_session_factory
from hop3.server.cli import Command

# Scan and load all RPC commands
scan_package("hop3.commands")


def format_table(headers: list[str], rows: list[list]) -> str:
    """Format a table for console output.

    Args:
        headers: List of column headers
        rows: List of rows (each row is a list of values)

    Returns:
        Formatted table string
    """
    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    # Format header
    header_line = "  ".join(
        h.ljust(w) for h, w in zip(headers, col_widths, strict=False)
    )
    separator = "  ".join("-" * w for w in col_widths)

    # Format rows
    row_lines = []
    for row in rows:
        row_line = "  ".join(
            str(cell).ljust(w) for cell, w in zip(row, col_widths, strict=False)
        )
        row_lines.append(row_line)

    return "\n".join([header_line, separator] + row_lines)


def _format_dict_item(item: dict) -> str:
    """Format a single dictionary item based on its type.

    Args:
        item: Dictionary with 't' (type) field

    Returns:
        Formatted string
    """
    item_type = item.get("t")
    if item_type == "text":
        return item.get("text", "")
    if item_type == "error":
        return f"ERROR: {item.get('text', '')}"
    if item_type == "success":
        return f"SUCCESS: {item.get('text', '')}"
    if item_type == "table":
        headers = item.get("headers", [])
        rows = item.get("rows", [])
        return format_table(headers, rows)
    # Unknown format
    return json.dumps(item, indent=2)


def _format_list_result(result: list) -> str:
    """Format list of message dicts.

    Args:
        result: List of items (dicts or other)

    Returns:
        Formatted string
    """
    output_parts = []
    for item in result:
        if isinstance(item, dict):
            output_parts.append(_format_dict_item(item))
        else:
            output_parts.append(str(item))
    return "\n".join(output_parts)


def format_output(result):
    """Format command result for console output.

    RPC commands return results in various formats (lists of dicts, plain text, etc).
    This function formats them appropriately for terminal display.

    Args:
        result: The result from the RPC command

    Returns:
        Formatted string for console output
    """
    if isinstance(result, list):
        return _format_list_result(result)
    if isinstance(result, dict):
        return _format_dict_item(result)
    if isinstance(result, str):
        return result
    # Fallback: JSON representation
    return json.dumps(result, indent=2)


def execute_rpc_command(command_name: str, args: list[str]) -> int:
    """Execute an RPC command locally.

    This reuses the logic from the RPC handler but executes directly on the server
    without going through the network layer.

    Args:
        command_name: Name of the command to execute (e.g., "apps", "auth:whoami")
        args: Arguments to pass to the command

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Get all registered RPC commands
    rpc_commands = {cmd.name: cmd for cmd in lookup(RpcCommand)}

    command_class = rpc_commands.get(command_name)
    if command_class is None:
        print(f"Error: Command '{command_name}' not found", file=sys.stderr)
        print("\nAvailable commands:", file=sys.stderr)
        for name in sorted(rpc_commands.keys()):
            cmd_class = rpc_commands[name]
            doc = cmd_class.__doc__ or ""
            # Get first line of docstring
            doc_line = doc.strip().split("\n")[0] if doc else ""
            print(f"  {name:<25} {doc_line}", file=sys.stderr)
        return 1

    # Create database session
    session_factory = get_session_factory()
    with session_factory() as db_session:
        # Prepare command initialization arguments
        class_args = {}

        # Check if command needs database session
        if "db_session" in command_class.__annotations__:
            class_args = {"db_session": db_session}

        try:
            # Instantiate the command
            command = command_class(**class_args)
        except Exception as e:
            print(f"Error: Failed to create command: {e}", file=sys.stderr)
            return 1

        try:
            # Execute the command
            result = command.call(*args)

            # Format and print the output
            output = format_output(result)
            print(output)

            return 0

        except Exception as e:
            print(f"Error: Command execution failed: {e}", file=sys.stderr)
            traceback.print_exc()
            return 1


@register
class Local(Command):
    """Execute RPC commands locally on the server.

    This command allows you to run hop3 commands directly on the server without
    going through the network/RPC layer. Useful for server administration and debugging.

    Examples:
        hop3-server local apps
        hop3-server local auth:whoami testuser
        hop3-server local config:set myapp KEY=value
        hop3-server local help

    Note: This bypasses authentication checks - only use for server administration.
    """

    name = "local"

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add command-specific arguments."""
        parser.add_argument(
            "command",
            type=str,
            help="RPC command to execute (e.g., 'apps', 'auth:whoami')",
        )
        parser.add_argument(
            "args",
            nargs="*",
            help="Arguments to pass to the command",
        )

    def run(self, command: str, args: list[str] | None = None):
        """Execute an RPC command locally.

        Args:
            command: The RPC command name
            args: Arguments to pass to the command
        """
        if args is None:
            args = []

        exit_code = execute_rpc_command(command, args)
        sys.exit(exit_code)
