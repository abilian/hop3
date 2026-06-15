# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI flag parsing and handling."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


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


def _get_env_no_input() -> bool:
    """Whether HOP3_NO_INPUT=1 requests non-interactive (no-prompt) mode.

    The counterpart to ``run_command_from_args``'s flag→env bridge: ``main``
    exports ``HOP3_NO_INPUT=1`` when ``--no-input`` is passed so deep prompt
    helpers can see it. Reading it back here lets a *caller's* environment
    (CI, scripts, the test harness running ``hop3 deploy`` via validoc) opt
    into non-interactive mode without threading ``--no-input`` onto every
    command — otherwise an interactive prompt blocks forever on a tty.
    """
    return os.environ.get("HOP3_NO_INPUT", "") == "1"


@dataclass(frozen=True)
class CliFlags:
    """CLI flags that control output and behavior."""

    json_output: bool = False  # --json, -j: Machine-readable JSON output
    skip_confirm: bool = False  # -y, --yes: Skip confirmation prompts

    # ADR 042 §D14: --force is the dedicated bypass for the project-
    # mismatch guard. It also implies skip_confirm (a --force user has
    # already opted into "yes really do it"), but the converse is NOT
    # true: -y/--yes alone must NOT silence the safety guard, or scripts
    # running `hop3 deploy -y` from the wrong directory deploy to the
    # wrong app — exactly the scenario the guard exists to prevent.
    force: bool = False

    # Verbosity is now stored as a level (0=quiet, 1=normal, 2=verbose, 3=debug)
    # This allows -vv, -vvv, -qq, etc.
    verbosity: int = field(default_factory=lambda: _get_env_verbosity() or 1)

    # Context override for multi-server support
    context: str | None = None  # --context <name>: Use a specific context

    # ADR 042: `--server` / `-s` selects a server from the global registry
    # explicitly. Highest-priority source in the server resolution chain;
    # bypasses any context-derived server.
    server: str | None = None

    # ADR 036 D5: `--app` / `-a` is always a flag, never positional.
    # ADR 036 D7: if not set, the CLI will resolve one via the app-resolution
    # chain (env, .hop3-app file, hop3.toml, context default).
    app: str | None = None

    # ADR 036: `--why` prints the resolution trace and exits without running
    # the command (diagnostic-only — avoids `hop3 deploy --why` deploying).
    why: bool = False

    # ADR 036: `--no-alias` bypasses alias resolution.
    no_alias: bool = False

    # ADR 036 D14 / G6: `--confirm <name>` is the scriptable alternative to
    # the interactive typed-name prompt. Carries the resource name the user
    # is acknowledging; e.g. `hop3 app destroy myapp --confirm=myapp`.
    confirm_value: str | None = None

    # ADR 036 G5: `--no-input` refuses to prompt; if input would be needed,
    # the command fails with a one-line "use --flag-X" instruction. For
    # automation/CI; complements `--yes` (which says "yes, take action").
    # Defaults from HOP3_NO_INPUT so a non-interactive environment opts in
    # without the flag (see _get_env_no_input).
    no_input: bool = field(default_factory=_get_env_no_input)

    # ADR 042 §Deploy preview: `--dry-run` prints the deploy plan and
    # exits without invoking the RPC. Analogous to `--why` but for the
    # action plan rather than the resolution trace.
    dry_run: bool = False

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


def _parse_verbosity_flag(arg: str, current: int) -> int | None:  # noqa: PLR0911 — mix of exact matches (--debug/--verbose/--quiet) and pattern matches (-v*/-d*/-q* with length-dependent verbosity); a unified table would have to encode the per-prefix length-to-level math and would read worse than the straight-line cascade.
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
    state: dict[str, Any] = {
        "json_output": False,
        "skip_confirm": False,
        "force": False,
        "context": None,
        "server": None,
        "app": None,
        "why": False,
        "no_alias": False,
        "confirm_value": None,
        # Default from the environment so a non-interactive caller (CI, the
        # tutorial/demo test harness) can set HOP3_NO_INPUT=1 once instead of
        # appending --no-input to every command. The flag still forces it on.
        "no_input": _get_env_no_input(),
        "dry_run": False,
        "verbosity": _get_env_verbosity() or 1,
    }

    remaining_args: list[str] = []
    i = 0
    while i < len(args):
        consumed = _apply_flag(args, i, state)
        if consumed == 0:
            remaining_args.append(args[i])
            i += 1
        else:
            i += consumed

    return CliFlags(**state), remaining_args


# Boolean flags: token → state field to set True. One row per logical flag,
# with aliases grouped in the tuple key.
_BOOL_FLAGS: dict[tuple[str, ...], str] = {
    ("--json", "-j"): "json_output",
    ("-y", "--yes"): "skip_confirm",
    ("--why",): "why",
    ("--no-alias",): "no_alias",
    ("--no-input",): "no_input",
    ("--dry-run",): "dry_run",
}


# --force needs its own row because it sets two flags at once: the
# §D14 bypass AND skip_confirm (a --force user has implicitly opted
# into the prompt skip). Handled in _apply_flag.
_FORCE_FLAG = "--force"

# Two-token "--flag value" pairs.
_PAIR_FLAGS: dict[tuple[str, ...], str] = {
    ("--context", "-c"): "context",
    ("--server", "-s"): "server",
    ("--app", "-a"): "app",
    ("--confirm",): "confirm_value",
}


def _apply_flag(args: list[str], i: int, state: dict[str, Any]) -> int:
    """Try to interpret args[i] as a flag; mutate state and return tokens consumed.

    Returns 0 when the token isn't a recognized flag (caller passes it through).
    Returns 1 for boolean/inline flags, 2 for ``--flag value`` pairs.
    """
    arg = args[i]

    if arg == _FORCE_FLAG:
        state["force"] = True
        state["skip_confirm"] = True
        return 1

    for keys, field_name in _BOOL_FLAGS.items():
        if arg in keys:
            state[field_name] = True
            return 1

    if arg.startswith("--confirm="):
        state["confirm_value"] = arg.split("=", 1)[1]
        return 1

    for keys, field_name in _PAIR_FLAGS.items():
        if arg in keys and i + 1 < len(args):
            state[field_name] = args[i + 1]
            return 2

    new_verbosity = _parse_verbosity_flag(arg, state["verbosity"])
    if new_verbosity is not None:
        state["verbosity"] = new_verbosity
        return 1

    return 0
