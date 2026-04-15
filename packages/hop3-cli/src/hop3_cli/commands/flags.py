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

    # Context override for multi-server support
    context: str | None = None  # --context <name>: Use a specific context

    # ADR 036 D5: `--app` / `-a` is always a flag, never positional.
    # ADR 036 D7: if not set, the CLI will resolve one via the app-resolution
    # chain (env, .hop3-app file, hop3.toml, context default).
    app: str | None = None

    # ADR 036: `--why` prints the resolution trace before running.
    why: bool = False

    # ADR 036: `--no-alias` bypasses alias resolution (placeholder for M3).
    no_alias: bool = False

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


def _parse_verbosity_flag(arg: str, current: int) -> int | None:
    """Parse a verbosity-related flag; return the new verbosity or None if not one."""
    if arg == "--debug":
        return 3
    if arg == "--verbose":
        return max(current, 2)
    if arg == "--quiet":
        return 0
    if arg.startswith("-") and arg[1:] and all(c == "v" for c in arg[1:]):
        # Handle -v, -vv, -vvv  (len 2 → 2, len 3 → 3, len ≥4 → 3)
        return min(3, len(arg))
    if arg.startswith("-") and arg[1:] and all(c == "d" for c in arg[1:]):
        # Handle -d, -dd, -ddd  (equivalent to -vv and -vvv)
        return min(3, 1 + len(arg))
    if arg.startswith("-") and arg[1:] and all(c == "q" for c in arg[1:]):
        # Handle -q, -qq (both mean quiet)
        return 0
    return None


def parse_flags(args: list[str]) -> tuple[CliFlags, list[str]]:
    """Parse CLI flags from arguments and return flags + remaining args.

    Supports:
        --json, -j: Machine-readable JSON output
        -y, --yes, --force: Skip confirmation prompts
        -v, --verbose: Increase verbosity (can stack: -vv, -vvv)
        -d, --debug: Debug mode (can stack: -d, -dd, -ddd)
        -q, --quiet: Decrease verbosity (can stack: -qq)
        --context <name>: Use a specific server context

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

        >>> parse_flags(['deploy', 'my-app', '-d'])
        (CliFlags(verbosity=2, ...), ['deploy', 'my-app'])

        >>> parse_flags(['apps', '--context', 'production'])
        (CliFlags(context='production', ...), ['apps'])
    """
    json_output = False
    skip_confirm = False
    context = None
    app: str | None = None
    why = False
    no_alias = False

    # Start with environment default or normal (1)
    verbosity = _get_env_verbosity() or 1

    # Flags to recognize
    json_flags = {"--json", "-j"}
    yes_flags = {"-y", "--yes", "--force"}

    # Filter out flags from args
    remaining_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in json_flags:
            json_output = True
        elif arg in yes_flags:
            skip_confirm = True
        elif arg in {"--context", "-c"} and i + 1 < len(args):
            context = args[i + 1]
            i += 1  # Skip the next arg (context name)
        elif arg in {"--app", "-a"} and i + 1 < len(args):
            app = args[i + 1]
            i += 1  # Skip the next arg (app name)
        elif arg == "--why":
            why = True
        elif arg == "--no-alias":
            no_alias = True
        elif (new_verbosity := _parse_verbosity_flag(arg, verbosity)) is not None:
            verbosity = new_verbosity
        else:
            # Not a flag, keep it
            remaining_args.append(arg)
        i += 1

    flags = CliFlags(
        json_output=json_output,
        skip_confirm=skip_confirm,
        verbosity=verbosity,
        context=context,
        app=app,
        why=why,
        no_alias=no_alias,
    )

    return flags, remaining_args
