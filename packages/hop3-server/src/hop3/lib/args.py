# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Declarative command-line argument parser for RPC commands.

This module provides a simple, declarative way to parse command-line arguments
passed through the RPC interface. It supports positional arguments, short/long
options, boolean flags, type conversion, default values, and collecting
remaining arguments.

Example usage:
    from hop3.lib.args import parse_cli_args

    # Define argument specification
    ARG_SPEC = {
        "app_name": {"positional": True},
        "lines": {"short": "-n", "type": int, "default": 100},
        "grep": {"type": str, "default": ""},
        "verbose": {"flag": True, "default": False},
    }

    # Parse arguments
    parsed = parse_cli_args(("myapp", "-n", "50", "--verbose"), ARG_SPEC)
    # Result: {"app_name": "myapp", "lines": 50, "grep": "", "verbose": True}

    # With remaining args (for commands that take multiple values):
    ARG_SPEC = {
        "app_name": {"positional": True},
        "keys": {"remaining": True},  # Collects all remaining non-option args
    }
    parsed = parse_cli_args(("myapp", "KEY1", "KEY2", "KEY3"), ARG_SPEC)
    # Result: {"app_name": "myapp", "keys": ["KEY1", "KEY2", "KEY3"]}
"""

from __future__ import annotations

from typing import Any


def _handle_short_option(
    arg: str,
    args_list: list,
    i: int,
    short_opts: dict[str, str],
    spec: dict[str, dict],
    result: dict[str, Any],
) -> int | None:
    """Handle short option like -n 50.

    Returns:
        New index if handled, None otherwise.
    """
    if arg in short_opts and i + 1 < len(args_list):
        key = short_opts[arg]
        converter = spec[key].get("type", str)
        result[key] = converter(args_list[i + 1])
        return i + 2
    return None


def _handle_long_option(
    arg: str,
    args_list: list,
    i: int,
    flags: set[str],
    spec: dict[str, dict],
    result: dict[str, Any],
) -> int | None:
    """Handle long option like --verbose, --key=value, or --key value.

    Returns:
        New index if handled, None otherwise.
    """
    if not arg.startswith("--"):
        return None

    key = arg[2:].replace("-", "_")

    # Handle flags: --verbose
    if key in flags:
        result[key] = True
        return i + 1

    # Handle --key=value format
    if "=" in arg:
        key, value = arg[2:].split("=", 1)
        key = key.replace("-", "_")
        if key in spec:
            converter = spec[key].get("type", str)
            result[key] = converter(value)
        return i + 1

    # Handle --key value format
    if key in spec and i + 1 < len(args_list):
        next_arg = args_list[i + 1]
        if not next_arg.startswith("-"):
            converter = spec[key].get("type", str)
            result[key] = converter(next_arg)
            return i + 2

    return i + 1


def _handle_positional_arg(
    arg: str,
    positional: str | None,
    remaining_key: str | None,
    result: dict[str, Any],
) -> bool:
    """Handle non-option argument (positional or remaining).

    Returns:
        True if handled, False otherwise.
    """
    if arg.startswith("-"):
        return False

    # First, fill the positional argument
    if positional and positional not in result:
        result[positional] = arg
        return True

    # Then, collect into remaining if specified
    if remaining_key:
        result[remaining_key].append(arg)
        return True

    return False


def parse_cli_args(
    args: tuple | list,
    spec: dict[str, dict],
) -> dict[str, Any]:
    """Parse CLI arguments declaratively.

    Args:
        args: Tuple or list of command-line arguments
        spec: Argument specification dict. Each key is the argument name, and the value
              is a dict with options:
              - "positional": True if this is a positional arg (first non-flag argument)
              - "remaining": True to collect all remaining non-option args as a list
              - "short": Short option form (e.g., "-n")
              - "flag": True if this is a boolean flag (no value)
              - "type": Type converter (e.g., int, str). Default is str.
              - "default": Default value if not provided

    Returns:
        Dict of parsed argument names to values

    Example:
        >>> spec = {
        ...     "app_name": {"positional": True},
        ...     "lines": {"short": "-n", "type": int, "default": 100},
        ...     "grep": {"type": str},
        ...     "since_deploy": {"flag": True},
        ... }
        >>> parse_cli_args(("myapp", "-n", "50"), spec)
        {'app_name': 'myapp', 'lines': 50}
    """
    result: dict[str, Any] = {}
    args_list = list(args)
    i = 0

    # Build lookup tables for efficient matching
    short_opts = {v["short"]: k for k, v in spec.items() if "short" in v}
    flags = {k for k, v in spec.items() if v.get("flag")}
    positional = next((k for k, v in spec.items() if v.get("positional")), None)
    remaining_key = next((k for k, v in spec.items() if v.get("remaining")), None)

    # Initialize remaining list if specified
    if remaining_key:
        result[remaining_key] = []

    while i < len(args_list):
        arg = args_list[i]

        # Try short option: -n 50
        new_i = _handle_short_option(arg, args_list, i, short_opts, spec, result)
        if new_i is not None:
            i = new_i
            continue

        # Try long option: --verbose, --key=value, --key value
        new_i = _handle_long_option(arg, args_list, i, flags, spec, result)
        if new_i is not None:
            i = new_i
            continue

        # Try positional or remaining argument
        if _handle_positional_arg(arg, positional, remaining_key, result):
            i += 1
            continue

        i += 1

    # Apply defaults
    for key, opts in spec.items():
        if key not in result and "default" in opts:
            result[key] = opts["default"]

    return result
