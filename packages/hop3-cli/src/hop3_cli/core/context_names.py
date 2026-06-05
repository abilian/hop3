# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Context-name validation (ADR 042 §Reserved context names).

A focused mirror of the server-side schema's validation rules. The CLI
duplicates the rules here so that ``hop3 context add`` and
``hop3 context init`` reject bad names *before* writing them to
``hop3.toml`` — without taking a runtime dependency on ``hop3-server``.

KEEP IN SYNC with ``packages/hop3-server/src/hop3/project/schema.py``
(``_CONTEXT_NAME_RE``, ``_RESERVED_CONTEXT_NAMES``, ``_validate_context_name``).
The two implementations are intentionally independent so the CLI can be
shipped without the server package, but their accepted/rejected sets
must agree. A drift test in the test suite pins this.
"""

from __future__ import annotations

import re

# Context names live in user-facing flags (``hop3 context use <name>``)
# and in ``.hop3-local.toml [current].context``. Same regex as the
# schema: start with a letter, then letters / digits / dash / underscore.
_CONTEXT_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")

# Reserved for current/future CLI keywords. Comparison is case-insensitive.
_RESERVED_CONTEXT_NAMES: frozenset[str] = frozenset({
    "default",
    "current",
    "global",
    "all",
    "none",
})


class InvalidContextNameError(ValueError):
    """Raised when a context name fails CLI-side validation.

    Subclass of ValueError so callers using ``except ValueError`` still
    catch it. The message is operator-facing and names both the offending
    name and the rule it violated.
    """


def validate_context_name(name: str) -> None:
    """Raise InvalidContextNameError when ``name`` would fail the schema.

    Two checks, in order so the user sees the most specific error first:

    1. **Reserved names** (case-insensitive): ``default``, ``current``,
       ``global``, ``all``, ``none``.
    2. **Identifier shape**: ``^[a-zA-Z][a-zA-Z0-9_-]*$``.

    Mirrors the server-side ``_validate_context_name`` so a name accepted
    by the CLI will also be accepted by the schema at deploy time.
    """
    if name.lower() in _RESERVED_CONTEXT_NAMES:
        reserved = ", ".join(sorted(_RESERVED_CONTEXT_NAMES))
        msg = (
            f"Context name {name!r} is reserved for CLI keywords. "
            f"Reserved names (case-insensitive): {reserved}. "
            "Pick a different name."
        )
        raise InvalidContextNameError(msg)
    if not _CONTEXT_NAME_RE.match(name):
        msg = (
            f"Invalid context name {name!r}. Context names must start with "
            "a letter and contain only letters, digits, '-' or '_'."
        )
        raise InvalidContextNameError(msg)
