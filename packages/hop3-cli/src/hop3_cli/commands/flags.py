# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI flag parsing and handling."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get_env_verbosity() -> int | None:
    """Get verbosity from HOP3_VERBOSITY environment variable.

    Returns:
        Verbosity level (0-3) or None if not set or invalid
    """
    env_val = os.environ.get("HOP3_VERBOSITY", "").strip()
    if not env_val:
        return None
    try:
        level = int(env_val)
        return max(0, min(3, level))  # Clamp to 0-3
    except ValueError:
        return None


@dataclass(frozen=True)
class CliFlags:
    """CLI flags that control output and behavior."""

    json_output: bool = False  # --json, -j: Machine-readable JSON output
    skip_confirm: bool = False  # -y, --yes, --force: Skip confirmation prompts

    # Verbosity is now stored as a level (0=quiet, 1=normal, 2=verbose, 3=debug)
    # This allows -vv, -vvv, -qq, etc.
    verbosity: int = field(default_factory=lambda: _get_env_verbosity() or 1)

    @property
    def quiet(self) -> bool:
        """True if verbosity is 0 (quiet mode)."""
        return self.verbosity == 0

    @property
    def verbose(self) -> bool:
        """True if verbosity is 2 or higher (verbose mode)."""
        return self.verbosity >= 2

    @property
    def debug(self) -> bool:
        """True if verbosity is 3 (debug mode)."""
        return self.verbosity >= 3


def parse_flags(args: list[str]) -> tuple[CliFlags, list[str]]:
    """Parse CLI flags from arguments and return flags + remaining args.

    Supports:
        --json, -j: Machine-readable JSON output
        -y, --yes, --force: Skip confirmation prompts
        -v, --verbose: Increase verbosity (can stack: -vv, -vvv)
        -q, --quiet: Decrease verbosity (can stack: -qq)
        --debug: Maximum verbosity (level 3)

    Environment variable:
        HOP3_VERBOSITY: Set default verbosity level (0-3)

    Args:
        args: Command-line arguments (e.g., ['deploy', 'my-app', '--json', '-y'])

    Returns:
        Tuple of (CliFlags, remaining_args)
        remaining_args has flags removed

    Examples:
        >>> parse_flags(['deploy', 'my-app', '--json'])
        (CliFlags(json_output=True, ...), ['deploy', 'my-app'])

        >>> parse_flags(['destroy', 'my-app', '-y', '-vv'])
        (CliFlags(verbosity=3, skip_confirm=True, ...), ['destroy', 'my-app'])
    """
    json_output = False
    skip_confirm = False

    # Start with environment default or normal (1)
    verbosity = _get_env_verbosity() or 1

    # Flags to recognize
    json_flags = {"--json", "-j"}
    yes_flags = {"-y", "--yes", "--force"}

    # Filter out flags from args
    remaining_args = []
    for arg in args:
        if arg in json_flags:
            json_output = True
        elif arg in yes_flags:
            skip_confirm = True
        elif arg == "--debug":
            verbosity = 3
        elif arg == "--verbose":
            verbosity = max(verbosity, 2)
        elif arg == "--quiet":
            verbosity = 0
        elif arg.startswith("-") and all(c == "v" for c in arg[1:]):
            # Handle -v, -vv, -vvv
            verbosity = min(3, 1 + len(arg) - 1)  # -v=2, -vv=3, -vvv=3
        elif arg.startswith("-") and all(c == "q" for c in arg[1:]):
            # Handle -q, -qq (but -q is enough for quiet=0)
            verbosity = 0
        else:
            # Not a flag, keep it
            remaining_args.append(arg)

    flags = CliFlags(
        json_output=json_output,
        skip_confirm=skip_confirm,
        verbosity=verbosity,
    )

    return flags, remaining_args
