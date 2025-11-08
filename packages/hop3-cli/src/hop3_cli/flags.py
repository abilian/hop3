# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI flag parsing and handling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CliFlags:
    """CLI flags that control output and behavior."""

    json_output: bool = False  # --json, -j: Machine-readable JSON output
    quiet: bool = False  # --quiet, -q: Suppress non-error output
    skip_confirm: bool = False  # -y, --yes, --force: Skip confirmation prompts
    verbose: bool = False  # -v, --verbose: Show verbose output (future)


def parse_flags(args: list[str]) -> tuple[CliFlags, list[str]]:
    """Parse CLI flags from arguments and return flags + remaining args.

    Args:
        args: Command-line arguments (e.g., ['deploy', 'my-app', '--json', '-y'])

    Returns:
        Tuple of (CliFlags, remaining_args)
        remaining_args has flags removed

    Examples:
        >>> parse_flags(['deploy', 'my-app', '--json'])
        (CliFlags(json_output=True, ...), ['deploy', 'my-app'])

        >>> parse_flags(['destroy', 'my-app', '-y', '--quiet'])
        (CliFlags(quiet=True, skip_confirm=True, ...), ['destroy', 'my-app'])
    """
    json_output = False
    quiet = False
    skip_confirm = False
    verbose = False

    # Flags to recognize
    json_flags = {"--json", "-j"}
    quiet_flags = {"--quiet", "-q"}
    yes_flags = {"-y", "--yes", "--force"}
    verbose_flags = {"-v", "--verbose"}

    # Filter out flags from args
    remaining_args = []
    for arg in args:
        if arg in json_flags:
            json_output = True
        elif arg in quiet_flags:
            quiet = True
        elif arg in yes_flags:
            skip_confirm = True
        elif arg in verbose_flags:
            verbose = True
        else:
            # Not a flag, keep it
            remaining_args.append(arg)

    flags = CliFlags(
        json_output=json_output,
        quiet=quiet,
        skip_confirm=skip_confirm,
        verbose=verbose,
    )

    return flags, remaining_args
