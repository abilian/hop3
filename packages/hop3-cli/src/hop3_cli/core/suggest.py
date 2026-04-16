# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Did-you-mean suggestions for unknown commands and app names (ADR 036 D10).

Two complementary mechanisms:

1. **Closest-match suggestions** — given an unknown token (typed by the user)
   and a list of known candidates (commands, app names, etc.), find the
   handful of candidates within a small edit-distance and return them.
   Backed by `difflib.get_close_matches` from the standard library; no extra
   dependency.

2. **Colon → space migration suggestion** — special-cased for users who still
   have ADR-pre-D1 muscle memory. If the typed token contains a `:`, suggest
   the space-separated form explicitly (with a note explaining the change).
   This is M5.4 from the plan.

Both functions are pure — no I/O, no global state — so they're trivially
testable and safe to call from any error path.
"""

from __future__ import annotations

import difflib
from pathlib import Path

# Conservative defaults: 3 matches, cutoff 0.6 means roughly 1-2 character
# edits on short strings. Lower cutoff => noisier suggestions.
_MAX_SUGGESTIONS = 3
_CUTOFF = 0.6


def closest_matches(
    target: str,
    candidates: list[str],
    *,
    max_n: int = _MAX_SUGGESTIONS,
    cutoff: float = _CUTOFF,
) -> list[str]:
    """Return up to `max_n` candidates closest to `target`, by edit distance.

    Empty target or empty candidates → empty result. Order is by descending
    similarity (best match first). Uses difflib's SequenceMatcher under the
    hood; cutoff of 0.6 maps to roughly 1-2 typo edits on short tokens.
    """
    if not target or not candidates:
        return []
    return difflib.get_close_matches(target, candidates, n=max_n, cutoff=cutoff)


def colon_to_space_suggestion(token: str) -> str | None:
    """If `token` looks like the old colon-syntax (`config:set`), suggest space form.

    Returns the suggested space-form (e.g., `"config set"`) or None if the
    token doesn't contain a colon. Used by the unknown-command path so that
    users with old muscle memory get a helpful one-time nudge rather than a
    bare "command not found".

    The detection is intentionally simple: any `:` in the first token. This
    catches the common `config:set` / `app:logs` patterns; it also catches
    `addons:create` etc. False positives (e.g., users who somehow want a
    literal `:` in a command path) are unlikely given ADR D1's commitment.
    """
    if ":" not in token:
        return None
    return token.replace(":", " ")


def format_did_you_mean(
    typed: str,
    suggestions: list[str],
    *,
    label: str = "Did you mean",
) -> str:
    """Render a "Did you mean ...?" line from a list of suggestions.

    With one suggestion: `Did you mean 'foo'?`
    With multiple:       `Did you mean: 'foo', 'bar', 'baz'?`
    With none:           `""` (caller decides what to do — usually nothing).
    """
    if not suggestions:
        return ""
    if len(suggestions) == 1:
        return f"{label} '{suggestions[0]}'?"
    quoted = ", ".join(f"'{s}'" for s in suggestions)
    return f"{label}: {quoted}?"


def load_cached_commands(cache_path: Path | None = None) -> list[str]:
    """Load the cached server command list (one space-separated name per line).

    The cache is written by `hop3 completion --refresh`. Returns an empty list
    if the cache doesn't exist or can't be read — callers should treat that
    as "no suggestions available" rather than as an error.
    """
    if cache_path is None:
        cache_path = (
            Path.home() / ".cache" / "hop3" / "commands.txt"
        )
    if not cache_path.is_file():
        return []
    try:
        return [line.strip() for line in cache_path.read_text().splitlines() if line.strip()]
    except OSError:
        return []
