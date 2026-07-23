# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the expects-failure negative-test-case machinery.

Two layers:
  1. Loader parses `expects-failure = true` from test.toml (legacy
     standalone shape) AND from a [test] section in hop3.toml.
  2. Runner inverts deploy success/failure: a deploy that fails in an
     expects-failure test is a PASS; an unexpected success is a FAIL.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from hop3_testing.catalog.loader import (
    _overrides_from_hop3_test,
    _overrides_from_legacy_test_toml,
    _parse_test_definition,
    _under_bad_dir,
    generate_test_definition_from_hop3_toml,
)
from hop3_testing.catalog.models import (
    Priority,
    TestDefinition,
    TestRequirements,
    Tier,
)
from hop3_testing.exceptions import DeploymentError
from hop3_testing.results import ResultStore
from hop3_testing.results.store import _derive_status
from hop3_testing.runners import deployment as deployment_module
from hop3_testing.runners.deployment import DeploymentTestRunner

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class TestLoaderParsesExpectsFailure:
    def test_default_is_false(self):
        assert _overrides_from_hop3_test({}).get("expects_failure", False) is False
        assert (
            _overrides_from_legacy_test_toml({"test": {}}).get("expects_failure", False)
            is False
        )

    def test_hop3_test_section_expects_failure_true(self):
        section = {"expects-failure": True}
        assert _overrides_from_hop3_test(section)["expects_failure"] is True

    def test_legacy_test_toml_expects_failure_true(self):
        data = {"test": {"expects-failure": True}}
        assert _overrides_from_legacy_test_toml(data)["expects_failure"] is True

    def test_parse_standalone_test_toml_reads_expects_failure(self, tmp_path):
        data = {
            "test": {
                "name": "negative",
                "tier": "fast",
                "priority": "P0",
                "expects-failure": True,
            }
        }
        td = _parse_test_definition(data, tmp_path / "test.toml")
        assert td.expects_failure is True

    def test_hop3_toml_bad_app_is_auto_expects_failure(self):
        """
        A bad recipe under apps/bad/** is xfail even via hop3.toml (no flag).

        Regression: the hop3.toml path only honoured the explicit config flag,
        so docker/native bad recipes (which carry hop3.toml) were counted as
        real failures instead of expected ones.
        """
        td = generate_test_definition_from_hop3_toml(
            Path("apps/bad/real-apps-docker-bad/discourse"),
            {"metadata": {"id": "discourse"}},
        )
        assert td.expects_failure is True

    def test_hop3_toml_normal_app_is_not_expects_failure(self):
        td = generate_test_definition_from_hop3_toml(
            Path("apps/real-apps-native/edrix"),
            {"metadata": {"id": "edrix"}},
        )
        assert td.expects_failure is False


# ---------------------------------------------------------------------------
# Runner: minimal stubs so we exercise the branching without touching
# network, ssh, paramiko, or subprocess.
# ---------------------------------------------------------------------------


@dataclass
class _FakeSession:
    app_name: str = "fake-app"
    last_deploy_error: str | None = None
    last_deploy_output: str | None = None  # full transcript (runner → bundle)
    cleaned: bool = False
    prepared: bool = False
    will_fail: bool = True

    def prepare(self):
        self.prepared = True

    def deploy(self, deploy_timeout: int) -> None:
        if self.will_fail:
            msg = "simulated poetry rejection"
            self.last_deploy_error = msg
            raise DeploymentError(msg)

    def check_deployed(self) -> bool:
        return True

    def cleanup(self) -> None:
        self.cleaned = True


class _FakeTarget:
    """
    Stand-in for DeploymentTarget. The runner only touches it via
    _collect_runtime_logs, which we monkeypatch.
    """


def _negative_test_def() -> TestDefinition:
    return TestDefinition(
        name="negative",
        tier=Tier.FAST,
        priority=Priority.P0,
        requirements=TestRequirements(),
        expects_failure=True,
    )


def _positive_test_def() -> TestDefinition:
    return TestDefinition(
        name="positive",
        tier=Tier.FAST,
        priority=Priority.P0,
        requirements=TestRequirements(),
        expects_failure=False,
    )


class TestRunnerInvertsExpectsFailure:
    """
    The runner's `expects_failure` branch is threaded through
    `_handle_expects_failure`. We exercise it by invoking that method
    directly — it's small, and doing the full `run()` path would
    require stubbing DeploymentSession in several places.
    """

    def _make_runner(self, tmp_path) -> DeploymentTestRunner:
        # `_collect_runtime_logs` is imported at module level in
        # deployment.py; patch the binding there.
        setattr(  # ruff:ignore[set-attr-with-constant]
            deployment_module,
            "_collect_runtime_logs",
            lambda _target, _name: "",
        )
        return DeploymentTestRunner(target=cast("Any", _FakeTarget()), cleanup=True)

    def test_failed_deploy_with_expects_failure_yields_pass(self, tmp_path):
        runner = self._make_runner(tmp_path)
        session = _FakeSession(will_fail=True)
        result = runner._handle_expects_failure(
            test=_negative_test_def(),
            session=cast("Any", session),
            start_time=0.0,
            deploy_logs="simulated deploy output",
            deploy_failed=True,
            validation_results=[],
        )
        assert result.passed is True
        # Synthetic validation is appended so reports show the inversion.
        assert any(
            vr.validation_type == "expects_failure" for vr in result.validation_results
        )
        assert session.cleaned is True

    def test_unexpected_success_with_expects_failure_yields_fail(self, tmp_path):
        runner = self._make_runner(tmp_path)
        session = _FakeSession(will_fail=False)
        result = runner._handle_expects_failure(
            test=_negative_test_def(),
            session=cast("Any", session),
            start_time=0.0,
            deploy_logs="deploy went through",
            deploy_failed=False,
            validation_results=[],
        )
        assert result.passed is False
        assert "Unexpected deploy success" in (result.error or "")
        assert session.cleaned is True


class TestBadDirIsNegativeTest:
    """Apps under apps/bad/ are auto-marked expects_failure (path-based)."""

    def test_under_bad_dir_matches(self):
        assert _under_bad_dir(Path("apps/bad/real-apps-docker-bad/wekan/hop3.toml"))
        assert _under_bad_dir(Path("/home/x/apps/bad/foo/hop3.toml"))

    def test_under_bad_dir_excludes_normal_apps(self):
        assert not _under_bad_dir(Path("apps/real-apps-docker/invoice-ninja/hop3.toml"))
        assert not _under_bad_dir(None)


class TestStoreStatusForNegativeTests:
    """xfail (expected failure) vs xpass (bad recipe unexpectedly works)."""

    def _result(self, name, *, passed, expects_failure):
        test = SimpleNamespace(
            name=name,
            runner_type="deployment",
            tier=SimpleNamespace(value="fast"),
            priority=SimpleNamespace(value="P1"),
            expects_failure=expects_failure,
        )
        return SimpleNamespace(
            test=test,
            passed=passed,
            total_duration=1.0,
            error=None,
            deploy_logs="",
            runtime_logs="",
            validation_results=[],
            bundle=None,
        )

    def test_derive_status(self):
        assert (
            _derive_status(self._result("a", passed=True, expects_failure=False))
            == "pass"
        )
        assert (
            _derive_status(self._result("b", passed=False, expects_failure=False))
            == "fail"
        )
        # Runner inverts negative tests: passed=True => expected failure happened.
        assert (
            _derive_status(self._result("c", passed=True, expects_failure=True))
            == "xfail"
        )
        assert (
            _derive_status(self._result("d", passed=False, expects_failure=True))
            == "xpass"
        )

    def test_save_status_and_counts(self, tmp_path):
        db = tmp_path / "r.db"
        store = ResultStore(db_path=db)
        run = store.start_run(mode="nightly", target_type="ssh", target_name="t")
        store.save(self._result("bad-fail", passed=True, expects_failure=True))  # xfail
        store.save(
            self._result("bad-works", passed=False, expects_failure=True)
        )  # xpass
        store.save(
            self._result("real-fail", passed=False, expects_failure=False)
        )  # fail
        store.save(
            self._result("real-pass", passed=True, expects_failure=False)
        )  # pass

        uid = run.run_uid
        assert uid is not None
        got = store.get_run(uid)
        assert got is not None
        assert got.failed_tests == 1  # only the true failure is red
        assert got.passed_tests == 3  # pass + xfail + xpass are "not a failure"

        rows = dict(
            sqlite3.connect(db).execute("SELECT test_name, status FROM test_results")
        )
        assert rows == {
            "bad-fail": "xfail",
            "bad-works": "xpass",
            "real-fail": "fail",
            "real-pass": "pass",
        }


def test_test_definition_default_expects_failure_false():
    td = _positive_test_def()
    assert td.expects_failure is False


def test_test_definition_expects_failure_true():
    td = _negative_test_def()
    assert td.expects_failure is True


# pytest fixture side-effect: silence the `Path | Any` TYPE_CHECKING churn.
_: Any = Path
_: Any = pytest
