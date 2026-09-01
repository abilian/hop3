# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Structured "did you mean …?" failures (ADR 036 D10).

A failure that the operator can fix by typing something slightly different
carries the token they typed and the candidates that were valid at the point
of failure. The client renders the hint from that payload — it never has to
recover either half by parsing the error sentence, which is what the first
implementation did (one regex per suggestion site, coupled to server prose).

The candidate set lives here because this is where it is known: the command
registry, the app repository, the argument parser. The rendering lives in the
client, where the user's own dialect (`--context`, `--app`) is known.
"""

from __future__ import annotations

import difflib
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["DidYouMeanError", "SuggestionKind", "closest_matches"]

# 3 matches, cutoff 0.6: roughly one or two edits on a short token. Same
# numbers as the client's offline fallback (`hop3_cli.core.suggest`).
MAX_SUGGESTIONS = 3
CUTOFF = 0.6


class SuggestionKind(StrEnum):
    """What the operator got wrong. The client renders one phrasing per kind."""

    UNKNOWN_COMMAND = "unknown_command"
    UNKNOWN_APP = "unknown_app"
    UNKNOWN_ARGUMENT = "unknown_argument"


class DidYouMeanError(ValueError):
    """
    A failure the client can turn into a suggestion.

    ``data`` travels as the JSON-RPC ``error.data`` member. Subclasses
    ``ValueError`` so a client (or a caller) that knows nothing about the
    payload still gets the plain message and the existing exit-code mapping.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: SuggestionKind,
        typed: str,
        candidates: Iterable[str] = (),
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.data: dict[str, object] = {
            "kind": str(kind),
            "typed": typed,
            "candidates": list(candidates),
        }
        if hint:
            self.data["hint"] = hint


def closest_matches(typed: str, candidates: Iterable[str]) -> list[str]:
    """Return the candidates within a small edit distance of ``typed``."""
    pool = list(candidates)
    if not typed or not pool:
        return []
    return difflib.get_close_matches(typed, pool, n=MAX_SUGGESTIONS, cutoff=CUTOFF)
