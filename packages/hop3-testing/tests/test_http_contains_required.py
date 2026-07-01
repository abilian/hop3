# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""A green deployment test must assert app-specific body content (audit C8).

An HTTP validation that asserts only a status code (no `contains`) passes on a
bare 200 — a placeholder page, a 200-rendered error, or another app's
default_server content. The runner now requires at least one `contains` OR a
check.py, else it fails loud.
"""

from __future__ import annotations

from typing import Any, cast

from hop3_testing.catalog.models import (
    Priority,
    TestDefinition,
    TestRequirements,
    Tier,
    Validation,
    ValidationExpect,
)
from hop3_testing.runners.deployment import DeploymentTestRunner


class _FakeSession:
    """Returns a passing HTTP result so the post-guard validation loop succeeds."""

    def test_http_detailed(self, path: str, expected_status: Any) -> dict[str, Any]:
        return {
            "passed": True,
            "message": "ok",
            "details": {"body_preview": "Hello Wiki.js world", "status_code": 200},
        }


def _runner() -> DeploymentTestRunner:
    return DeploymentTestRunner(target=cast("Any", object()), cleanup=True)


def _test_def(validations: list[Validation]) -> TestDefinition:
    return TestDefinition(
        name="x",
        tier=Tier.FAST,
        priority=Priority.P0,
        requirements=TestRequirements(),
        validations=validations,
    )


def _app(*, check: bool = False, procfile: bool = False) -> Any:
    from types import SimpleNamespace  # noqa: PLC0415

    return SimpleNamespace(has_check_script=check, has_procfile=procfile)


def test_status_only_validation_without_check_fails_loud():
    results: list = []
    err = _runner()._run_http_validations(
        _test_def([
            Validation(type="http", path="/", expect=ValidationExpect(status=200))
        ]),
        cast("Any", None),
        _app(),
        results,
    )
    assert err is not None
    assert "bare-status" in err
    assert results[0].passed is False


def test_check_script_exempts_status_only_validation():
    results: list = []
    err = _runner()._run_http_validations(
        _test_def([
            Validation(type="http", path="/", expect=ValidationExpect(status=200))
        ]),
        cast("Any", _FakeSession()),
        _app(check=True),  # check.py asserts content -> exempt from the contains rule
        results,
    )
    assert err is None  # guard passes; the validation itself succeeded


def test_contains_satisfies_the_guard():
    results: list = []
    err = _runner()._run_http_validations(
        _test_def([
            Validation(
                type="http",
                path="/",
                expect=ValidationExpect(status=200, contains="Wiki.js"),
            )
        ]),
        cast("Any", _FakeSession()),
        _app(),
        results,
    )
    assert err is None


def test_procfile_without_validations_or_check_fails_loud():
    results: list = []
    err = _runner()._run_http_validations(
        _test_def([]),  # no http validations
        cast("Any", None),
        _app(procfile=True),
        results,
    )
    assert err is not None
    assert "no [[validations]]" in err
    assert results[0].passed is False
