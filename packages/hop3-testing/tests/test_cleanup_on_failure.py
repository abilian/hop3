# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Regression: cleanup must destroy the app even after a FAILED deploy.

A partial deploy can create the app and provision some addons (e.g. postgres
before redis failed). If cleanup skipped those, every failed deploy would leak
an app dir + addon slots — the slow cause of disk and Redis-db exhaustion.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from hop3_testing.apps.deployment import DeploymentSession
from hop3_testing.exceptions import CleanupError
from hop3_testing.runners.base import TestResult
from hop3_testing.runners.deployment import DeploymentTestRunner


def _session(*, deployed: bool) -> DeploymentSession:
    s = object.__new__(DeploymentSession)  # bypass heavy __init__
    s.app_name = "app-1"
    s.deployed = deployed
    s.console = MagicMock()
    s._preparation = MagicMock()
    return s


def test_cleanup_destroys_even_when_deploy_failed():
    s = _session(deployed=False)  # a failed deploy never set deployed=True
    with patch.object(DeploymentSession, "_destroy_app") as destroy:
        s.cleanup()
    destroy.assert_called_once()  # the partial app is still torn down
    cast("Any", s._preparation.cleanup).assert_called_once()


def test_cleanup_destroys_on_success_too():
    s = _session(deployed=True)
    with patch.object(DeploymentSession, "_destroy_app") as destroy:
        s.cleanup()
    destroy.assert_called_once()


def test_a_failed_destroy_is_reported_and_returned_not_raised():
    """Printed whatever the verbosity (a warning `--quiet` hid), and returned."""
    s = _session(deployed=False)
    with patch.object(
        DeploymentSession, "_destroy_app", side_effect=CleanupError("boom")
    ):
        problem = s.cleanup()  # must not raise
    assert problem is not None
    assert "boom" in problem
    cast("Any", s.console.error).assert_called_once()
    cast("Any", s._preparation.cleanup).assert_called_once()  # temp dir still cleaned


def test_a_failed_teardown_fails_the_with_block():
    """`with DeploymentSession(...)` must not pass while destroy left files."""
    s = _session(deployed=True)
    with (
        patch.object(
            DeploymentSession, "_destroy_app", side_effect=CleanupError("leftover")
        ),
        pytest.raises(CleanupError, match="leftover"),
        s,
    ):
        pass


def test_a_failed_teardown_does_not_replace_the_blocks_own_error():
    s = _session(deployed=True)
    with (
        patch.object(
            DeploymentSession, "_destroy_app", side_effect=CleanupError("leftover")
        ),
        pytest.raises(AssertionError, match="the real failure") as raised,
        s,
    ):
        msg = "the real failure"
        raise AssertionError(msg)
    # The teardown's problem travels with the error, into the test report.
    assert any("leftover" in note for note in raised.value.__notes__)


def _runner() -> DeploymentTestRunner:
    return DeploymentTestRunner(target=MagicMock(), console=MagicMock())


def _passed() -> TestResult:
    return TestResult(test=MagicMock(), passed=True)


def test_a_passing_test_whose_teardown_left_files_fails():
    session = MagicMock(cleanup=MagicMock(return_value="Permission denied"))
    result = _runner()._torn_down(_passed(), MagicMock(), session)
    assert not result.passed
    assert result.error == "Permission denied"


def test_a_clean_teardown_keeps_the_result():
    session = MagicMock(cleanup=MagicMock(return_value=None))
    result = _runner()._torn_down(_passed(), MagicMock(), session)
    assert result.passed
    assert result.error is None


def test_a_cleanup_that_raises_fails_the_test():
    session = MagicMock(cleanup=MagicMock(side_effect=OSError("disk gone")))
    result = _runner()._torn_down(_passed(), MagicMock(), session)
    assert not result.passed
    assert result.error is not None
    assert "disk gone" in result.error


def test_a_teardown_problem_follows_the_earlier_error():
    """The expects-failure PASS carries the deploy error; the teardown's comes after."""
    session = MagicMock(cleanup=MagicMock(return_value="leftover: src/"))
    earlier = TestResult(test=MagicMock(), passed=True, error="build rejected")
    result = _runner()._torn_down(earlier, MagicMock(), session)
    assert not result.passed
    assert result.error == "build rejected; teardown: leftover: src/"
