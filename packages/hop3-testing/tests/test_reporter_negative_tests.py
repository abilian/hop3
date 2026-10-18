# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A negative test's outcome must not be reported in the words used for a normal one.

An app under `broken/` is loaded with `expects_failure=True`, which inverts
`passed`: the runner sets it True when the deploy FAILED. The console reporter
printed that as `OK`, so a whole run of still-broken apps read as a run of
working ones, and the one app that had started working was printed under
"Failed tests:" above its own green "ok" headline.
"""

from __future__ import annotations

import io
import types
from pathlib import Path

from hop3_testing.results.reporters import ConsoleReporter


def _result(name: str, *, passed: bool, negative: bool, cause: str = ""):
    test = types.SimpleNamespace(
        name=name, expects_failure=negative, app_path=Path(name)
    )
    validations = []
    if cause:
        validations.append(
            types.SimpleNamespace(
                type_name="expects_failure",
                message=f"Deploy failed as expected (expects-failure=true): {cause}",
            )
        )
    return types.SimpleNamespace(
        test=test,
        passed=passed,
        total_duration=1.0,
        error=cause or None,
        bundle=None,
        runtime_logs="",
        validations=validations,
        unverified="",
        screenshots=None,
    )


def _render():
    rows = [
        _result(
            "apps/broken/directus",
            passed=True,
            negative=True,
            cause="Deploy failed: nix-build failed: undefined variable 'hedgedoc'",
        ),
        _result("apps/broken/xwiki-nix", passed=False, negative=True),
        _result("apps/golden/forgejo", passed=True, negative=False),
        _result("apps/alpha/piwigo", passed=False, negative=False),
    ]
    out = io.StringIO()
    reporter = ConsoleReporter(output=out)
    reporter.use_color = False
    reporter._print_per_app_results(rows)
    reporter._print_failed_tests(rows)
    return out.getvalue()


def test_negative_outcomes_get_their_own_words() -> None:
    text = _render()
    assert "apps/broken/directus: XFAIL (failed as expected:" in text
    assert "apps/broken/xwiki-nix: XPASS (did NOT fail as expected" in text


def test_an_expected_failure_names_its_cause() -> None:
    """
    "Failed as expected" alone proves something went wrong, not that the
    expected thing did — and it left an operator with nothing to act on.
    """
    text = _render()
    assert "undefined variable" in text


def test_normal_outcomes_are_unchanged() -> None:
    text = _render()
    assert "apps/golden/forgejo: OK" in text
    assert "apps/alpha/piwigo: FAIL" in text


def test_an_unexpected_deploy_is_not_listed_as_a_failed_test() -> None:
    text = _render()
    failed_block = text.split("Failed tests:")[1].split("Deployed unexpectedly")[0]
    assert "xwiki-nix" not in failed_block
    assert "piwigo" in failed_block
