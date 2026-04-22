# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Tests for the expects-failure negative-test-case machinery.

Two layers:
  1. Loader parses `expects-failure = true` from test.toml (legacy
     standalone shape) AND from a [test] section in hop3.toml.
  2. Runner inverts deploy success/failure: a deploy that fails in an
     expects-failure test is a PASS; an unexpected success is a FAIL.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from hop3_testing.catalog.loader import (
    _overrides_from_hop3_test,
    _overrides_from_legacy_test_toml,
    _parse_test_definition,
)
from hop3_testing.catalog.models import (
    Priority,
    TestDefinition,
    TestRequirements,
    Tier,
)
from hop3_testing.exceptions import DeploymentError
from hop3_testing.runners import deployment as deployment_module
from hop3_testing.runners.deployment import DeploymentTestRunner

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class TestLoaderParsesExpectsFailure:
    def test_default_is_false(self):
        assert _overrides_from_hop3_test({}).get("expects_failure", False) is False
        assert (
            _overrides_from_legacy_test_toml({"test": {}}).get(
                "expects_failure", False
            )
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


# ---------------------------------------------------------------------------
# Runner: minimal stubs so we exercise the branching without touching
# network, ssh, paramiko, or subprocess.
# ---------------------------------------------------------------------------


@dataclass
class _FakeSession:
    app_name: str = "fake-app"
    last_deploy_error: str | None = None
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
    """Stand-in for DeploymentTarget. The runner only touches it via
    _collect_runtime_logs, which we monkeypatch."""


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
    """The runner's `expects_failure` branch is threaded through
    `_handle_expects_failure`. We exercise it by invoking that method
    directly — it's small, and doing the full `run()` path would
    require stubbing DeploymentSession in several places."""

    def _make_runner(self, tmp_path) -> DeploymentTestRunner:
        # `_collect_runtime_logs` is imported at module level in
        # deployment.py; patch the binding there.
        deployment_module._collect_runtime_logs = (  # type: ignore[assignment]
            lambda _target, _name: ""
        )
        return DeploymentTestRunner(target=_FakeTarget(), cleanup=True)

    def test_failed_deploy_with_expects_failure_yields_pass(self, tmp_path):
        runner = self._make_runner(tmp_path)
        session = _FakeSession(will_fail=True)
        result = runner._handle_expects_failure(
            test=_negative_test_def(),
            session=session,  # type: ignore[arg-type]
            start_time=0.0,
            deploy_logs="simulated deploy output",
            deploy_failed=True,
            validation_results=[],
        )
        assert result.passed is True
        # Synthetic validation is appended so reports show the inversion.
        assert any(
            vr.validation_type == "expects_failure"
            for vr in result.validation_results
        )
        assert session.cleaned is True

    def test_unexpected_success_with_expects_failure_yields_fail(self, tmp_path):
        runner = self._make_runner(tmp_path)
        session = _FakeSession(will_fail=False)
        result = runner._handle_expects_failure(
            test=_negative_test_def(),
            session=session,  # type: ignore[arg-type]
            start_time=0.0,
            deploy_logs="deploy went through",
            deploy_failed=False,
            validation_results=[],
        )
        assert result.passed is False
        assert "Unexpected deploy success" in (result.error or "")
        assert session.cleaned is True


def test_test_definition_default_expects_failure_false():
    td = _positive_test_def()
    assert td.expects_failure is False


def test_test_definition_expects_failure_true():
    td = _negative_test_def()
    assert td.expects_failure is True


# pytest fixture side-effect: silence the `Path | Any` TYPE_CHECKING churn.
_: Any = Path
_: Any = pytest
