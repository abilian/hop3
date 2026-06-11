# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""A failed deployment test must still tear its app down.

Regression for the owncast 1935 leak: the runner's failure early-returns
(`_fail_result`) used to skip cleanup — only the success path tore down. A
deploy that committed its fixed-port claim but then failed validation left the
app (and its claim) behind, blocking the next deploy of that port. The runner
must clean up on EVERY outcome (unless cleanup is explicitly disabled).
"""

from __future__ import annotations

from typing import Any, cast

from hop3_testing.catalog.models import (
    DeploymentConfig,
    Priority,
    TestDefinition,
    TestRequirements,
    Tier,
)
from hop3_testing.exceptions import DeploymentError
from hop3_testing.runners import deployment as deployment_module
from hop3_testing.runners.deployment import DeploymentTestRunner


class _FakeTarget:
    def ensure_disk_headroom(self) -> None:
        pass


class _FakeSession:
    def __init__(self, **_kwargs):
        self.app_name = "owncast-x"
        self.last_deploy_error = "RTMP daemon failed to bind"
        self.cleaned = False

    def prepare(self) -> None:
        pass

    def deploy(self, deploy_timeout: int) -> None:
        raise DeploymentError(self.last_deploy_error)

    def cleanup(self) -> None:
        self.cleaned = True


def _failing_test(tmp_path) -> TestDefinition:
    # app_path is derived: source_path.parent / deployment.path ('.') == tmp_path.
    return TestDefinition(
        name="owncast",
        tier=Tier.FAST,
        priority=Priority.P0,
        requirements=TestRequirements(),
        deployment=DeploymentConfig(path="."),
        source_path=tmp_path / "test.toml",
    )


def _install_fakes(monkeypatch) -> dict[str, _FakeSession]:
    created: dict[str, _FakeSession] = {}

    def _factory(**kwargs):
        created["session"] = _FakeSession(**kwargs)
        return created["session"]

    monkeypatch.setattr(deployment_module, "_collect_runtime_logs", lambda *a: "")
    monkeypatch.setattr(deployment_module, "DeploymentSession", _factory)
    monkeypatch.setattr(
        DeploymentTestRunner, "_collect_bundle", lambda self, *a, **k: None
    )
    return created


def test_failed_deploy_is_cleaned_up(tmp_path, monkeypatch):
    created = _install_fakes(monkeypatch)
    runner = DeploymentTestRunner(target=cast("Any", _FakeTarget()), cleanup=True)

    result = runner.run(_failing_test(tmp_path))

    assert result.passed is False
    assert "Deploy failed" in (result.error or "")
    # The crux: the failed deploy was still torn down (no leaked app/claim).
    assert created["session"].cleaned is True


def test_failed_deploy_skips_cleanup_when_disabled(tmp_path, monkeypatch):
    # With cleanup=False (e.g. --keep for debugging), a failure must NOT tear down.
    created = _install_fakes(monkeypatch)
    runner = DeploymentTestRunner(target=cast("Any", _FakeTarget()), cleanup=False)

    runner.run(_failing_test(tmp_path))

    assert created["session"].cleaned is False
