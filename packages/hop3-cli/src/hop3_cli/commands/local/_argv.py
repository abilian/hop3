# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The argv parser the local commands share.

Each local command used to walk argv in its own loop ending in
``else: i += 1``, so a typo'd flag (``--usrname admin``) was dropped and the
command ran without it. This parser refuses every token it was not told about.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, NoReturn

from hop3_cli.exit_codes import ExitCode

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class LocalArgs:
    """What ``parse_local_args`` found: flag values, switches, positionals."""

    values: Mapping[str, str | None] = field(default_factory=dict)
    switches: frozenset[str] = frozenset()
    positionals: tuple[str, ...] = ()

    def get(self, flag: str) -> str | None:
        """The value of ``flag``, or None when absent or given without one."""
        return self.values.get(flag)


def parse_local_args(
    args: list[str],
    *,
    usage: str,
    value_flags: frozenset[str] = frozenset(),
    optional_value_flags: frozenset[str] = frozenset(),
    switches: frozenset[str] = frozenset(),
    max_positionals: int = 0,
) -> LocalArgs:
    """
    Parse ``args`` against the flags a command declares; refuse anything else.

    ``value_flags`` need a value. ``optional_value_flags`` may stand alone (at
    the end, or before another flag): their value is then None, which the
    caller reads as "prompt for it". A value never starts with a dash, so
    ``--url --tokn`` is a missing value and not the URL ``--tokn``; ``-`` alone
    is a value (stdin, ADR 036 §D14). A flag given twice is refused: the
    last one silently won.
    """
    values: dict[str, str | None] = {}
    seen: set[str] = set()
    positionals: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in values or arg in seen:
            usage_failure(f"{arg} is given twice.", usage)
        following = args[i + 1] if i + 1 < len(args) else None
        has_value = following is not None and not _is_flag(following)
        if arg in value_flags:
            if not has_value:
                usage_failure(f"{arg} needs a value.", usage)
            values[arg] = following
            i += 2
        elif arg in optional_value_flags:
            values[arg] = following if has_value else None
            i += 2 if has_value else 1
        elif arg in switches:
            seen.add(arg)
            i += 1
        elif _is_flag(arg):
            usage_failure(f"unknown option {arg!r}.", usage)
        else:
            positionals.append(arg)
            i += 1
    if len(positionals) > max_positionals:
        extra = " ".join(positionals[max_positionals:])
        usage_failure(f"unexpected argument(s): {extra}", usage)
    return LocalArgs(MappingProxyType(values), frozenset(seen), tuple(positionals))


def _is_flag(token: str) -> bool:
    """Whether ``token`` is a flag: dash-led, except ``-`` (stdin)."""
    return token.startswith("-") and token != "-"


def usage_failure(message: str, usage: str) -> NoReturn:
    """Print ``message`` and the usage line on stderr, exit USAGE_ERROR (2)."""
    print(f"Error: {message}\n{usage}", file=sys.stderr)
    sys.exit(ExitCode.USAGE_ERROR)
