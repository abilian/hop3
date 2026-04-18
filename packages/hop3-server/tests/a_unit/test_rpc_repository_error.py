# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for RepositoryError → Diagnosis unwrapping in the RPC controller."""

from __future__ import annotations

import pytest
from advanced_alchemy.exceptions import (
    DuplicateKeyError,
    ForeignKeyError,
    IntegrityError,
    MultipleResultsFoundError,
    NotFoundError,
    RepositoryError,
)

from hop3.server.controllers.rpc import (
    _extract_repository_error_reason,
    _repository_error_diagnosis,
)


def _with_cause(exc_cls, detail: str, cause_msg: str) -> RepositoryError:
    """Construct a RepositoryError with a synthetic underlying SQLAlchemy cause."""
    try:
        raise ValueError(cause_msg)
    except ValueError as cause:
        try:
            raise exc_cls(detail=detail) from cause
        except exc_cls as wrapped:
            return wrapped


class TestExtractReason:
    def test_prefers_cause_over_generic_detail(self) -> None:
        exc = _with_cause(
            RepositoryError,
            detail="There was an error during data processing",
            cause_msg="UNIQUE constraint failed: app.name",
        )
        assert (
            _extract_repository_error_reason(exc)
            == "UNIQUE constraint failed: app.name"
        )

    def test_falls_back_to_detail_when_no_cause(self) -> None:
        # Skip the cause-wiring helper for this case
        exc = RepositoryError(detail="custom detail text")
        assert _extract_repository_error_reason(exc) == "custom detail text"

    def test_generic_detail_without_cause_returns_placeholder(self) -> None:
        exc = RepositoryError(detail="There was an error during data processing")
        reason = _extract_repository_error_reason(exc)
        assert "no additional details" in reason


class TestDiagnosisBySubclass:
    @pytest.mark.parametrize(
        ("exc_cls", "expected_action"),
        [
            (DuplicateKeyError, "insert or update record"),
            (ForeignKeyError, "satisfy foreign-key constraint"),
            (IntegrityError, "satisfy integrity constraint"),
            (NotFoundError, "find record"),
            (MultipleResultsFoundError, "resolve record"),
        ],
    )
    def test_subclass_produces_tailored_action(
        self, exc_cls, expected_action: str
    ) -> None:
        exc = _with_cause(
            exc_cls,
            detail="There was an error during data processing",
            cause_msg="simulated underlying failure",
        )
        diag = _repository_error_diagnosis(exc)
        assert diag.component == "Database"
        assert diag.action == expected_action
        assert "simulated underlying failure" in diag.reason

    def test_bare_repository_error_falls_back_to_generic(self) -> None:
        exc = _with_cause(
            RepositoryError,
            detail="There was an error during data processing",
            cause_msg="OperationalError: server closed the connection",
        )
        diag = _repository_error_diagnosis(exc)
        assert diag.action == "execute repository operation"
        assert "server closed the connection" in diag.reason
        # Generic fallback always provides troubleshooting
        assert diag.troubleshooting


class TestDuplicateKeyHintMentionsRename:
    def test_hint_offers_actionable_suggestion(self) -> None:
        exc = _with_cause(
            DuplicateKeyError,
            detail="There was an error during data processing",
            cause_msg="duplicate key value violates unique constraint",
        )
        diag = _repository_error_diagnosis(exc)
        assert "different name" in diag.hint.lower() or "delete" in diag.hint.lower()
