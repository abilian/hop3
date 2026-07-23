# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3 aliases` — list all effective aliases with source and expansion.

Per ADR 036 D9, this is the introspection command for the alias subsystem.
It lists every alias in the effective registry with:

- source token (what the user types)
- expansion (the canonical tokens it resolves to)
- origin (built-in, plugin, or user)
- origin detail (e.g., config file path) when applicable

It also reports any user aliases that were skipped due to collisions with
core or plugin aliases.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from hop3_cli.core.alias_registry import (
    build_registry,
    load_user_aliases_with_diagnostics,
)

if TYPE_CHECKING:
    from hop3_cli.config import Config
    from hop3_cli.ui.rich_printer import RichPrinter


def handle_aliases(args: list[str], config: Config, printer: RichPrinter) -> None:
    """Handle the `hop3 aliases` command."""
    if "--help" in args or "-h" in args:
        _show_help()
        return

    user, diags = load_user_aliases_with_diagnostics(config.config_file)
    registry = build_registry(user_aliases=user)

    # Surface load-time diagnostics first so users notice broken config.
    if diags.parse_error:
        print(f"Warning: {diags.parse_error}", file=sys.stderr)
    for token, reason in diags.rejected:
        print(f"Warning: alias {token!r} skipped: {reason}", file=sys.stderr)
    if diags.parse_error or diags.rejected:
        print(file=sys.stderr)  # blank line between warnings and the table

    if not registry.aliases and not registry.skipped:
        print("No aliases defined.")
        return

    # Effective aliases, sorted by source_token for stable output.
    rows = sorted(registry.aliases.values(), key=lambda a: a.source_token)
    token_width = max(len(a.source_token) for a in rows) if rows else 10
    expansion_width = max(len(" ".join(a.expansion)) for a in rows) if rows else 10

    header_token = "ALIAS".ljust(token_width)
    header_exp = "EXPANSION".ljust(expansion_width)
    print(f"{header_token}  {header_exp}  SOURCE")
    print(f"{'-' * token_width}  {'-' * expansion_width}  ------")
    for a in rows:
        expansion = " ".join(a.expansion)
        # Widen from Literal["built-in","plugin","user"] to str so we can
        # annotate the user row with its source-file path.
        origin: str = a.origin
        if a.origin_detail and a.origin == "user":
            origin = f"user ({a.origin_detail})"
        print(
            f"{a.source_token.ljust(token_width)}  "
            f"{expansion.ljust(expansion_width)}  {origin}"
        )

    if registry.skipped:
        print()
        print("Skipped user aliases (collision with core or plugin):", file=sys.stderr)
        for token, reason in registry.skipped:
            print(f"  - {token}: {reason}", file=sys.stderr)


def _show_help() -> None:
    from .help_text import ALIASES_HELP  # ruff:ignore[import-outside-top-level]

    print(ALIASES_HELP)
