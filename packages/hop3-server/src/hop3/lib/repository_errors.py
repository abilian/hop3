# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Shared helpers for turning advanced_alchemy RepositoryErrors into a
structured `Diagnosis`.

Used by both the JSON-RPC controller (`hop3/server/controllers/rpc.py`)
and the hop3-server CLI entry point (`hop3/server/cli/cli.py`). Keeping
the logic in one place means a `git push` (which drives deployment
through the CLI) and a direct RPC call produce the same actionable
error message instead of advanced_alchemy's generic "There was an
error during data processing" leaking to the user.
"""

from __future__ import annotations

from advanced_alchemy.exceptions import (
    DuplicateKeyError,
    ForeignKeyError,
    IntegrityError,
    MultipleResultsFoundError,
    NotFoundError,
    RepositoryError,
)

from hop3.lib.diagnostics import Diagnosis, format_diagnosis

_GENERIC_AA_MESSAGES = frozenset({
    "There was an error during data processing",
    "An exception occurred",
})


def extract_repository_error_reason(exc: RepositoryError) -> str:
    """
    Extract the most specific available cause from a RepositoryError.

    advanced_alchemy wraps SQLAlchemy exceptions with a generic top-level
    ``detail`` ("There was an error during data processing"). The real
    cause lives on ``__cause__`` (the original SQLAlchemy exception).
    Prefer the cause, then the detail, then the string form — skipping
    generic placeholders at every step.
    """
    if exc.__cause__:
        cause_msg = str(exc.__cause__).strip()
        if cause_msg:
            return cause_msg

    if exc.detail and exc.detail not in _GENERIC_AA_MESSAGES:
        return exc.detail

    exc_str = str(exc).strip()
    if exc_str and exc_str not in _GENERIC_AA_MESSAGES:
        return exc_str

    return "database operation failed (no additional details available)"


def repository_error_diagnosis(exc: RepositoryError) -> Diagnosis:
    """
    Build a structured Diagnosis for a RepositoryError.

    Inspects the exception subclass to produce a tailored action / hint /
    troubleshooting list. Falls back to a generic Database diagnosis when
    the subclass is not one we recognise.
    """
    reason = extract_repository_error_reason(exc)

    if isinstance(exc, DuplicateKeyError):
        return Diagnosis(
            component="Database",
            action="insert or update record",
            reason=f"duplicate key: {reason}",
            hint=(
                "An entity with this name / identifier already exists. "
                "Choose a different name, or delete the existing record first."
            ),
            troubleshooting=[
                "hop3 app list  (or the equivalent list command for this resource)",
            ],
        )

    if isinstance(exc, ForeignKeyError):
        return Diagnosis(
            component="Database",
            action="satisfy foreign-key constraint",
            reason=f"foreign-key violation: {reason}",
            hint=(
                "The referenced parent record doesn't exist or is still in use. "
                "Create the parent first, or detach dependents before deleting."
            ),
        )

    if isinstance(exc, IntegrityError):
        return Diagnosis(
            component="Database",
            action="satisfy integrity constraint",
            reason=f"integrity violation: {reason}",
            hint=(
                "A NOT NULL / UNIQUE / CHECK constraint was violated. "
                "Review the submitted values against the model's constraints."
            ),
        )

    if isinstance(exc, NotFoundError):
        return Diagnosis(
            component="Database",
            action="find record",
            reason=f"not found: {reason}",
            hint=(
                "The target record does not exist. Verify the identifier and "
                "that it belongs to the current context."
            ),
        )

    if isinstance(exc, MultipleResultsFoundError):
        return Diagnosis(
            component="Database",
            action="resolve record",
            reason=f"multiple rows matched a single-row query: {reason}",
            hint="Narrow the query — the identifier is ambiguous across contexts.",
        )

    return Diagnosis(
        component="Database",
        action="execute repository operation",
        reason=reason,
        hint=(
            "Retry the command; if the error persists, the database may be "
            "out of sync with the app state"
        ),
        troubleshooting=[
            "hop3 system logs",
            "hop3 system check",
        ],
    )


def format_repository_error(exc: RepositoryError) -> str:
    """Return the formatted Diagnosis string for a RepositoryError."""
    return format_diagnosis(repository_error_diagnosis(exc))
