# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The cloud DeploymentManager delegates to the shared run_hop3_deploy (7b).

ADR 052 Phase 7b collapses the two deploy wrappers: DeploymentManager.deploy()
no longer builds/runs its own subprocess — it delegates to run_hop3_deploy
(targets.helpers), so the cloud path and the `run` path build+stream the deploy
identically (one command-builder, one runner). These tests pin the delegation +
result shaping; the stdin=DEVNULL / process-group-killed-timeout guarantees are
pinned on the shared runner in test_streaming.py.
"""

from __future__ import annotations

from hop3_testing.system_tests import deployment as depmod
from hop3_testing.system_tests.config import DeploymentConfig
from hop3_testing.system_tests.deployment import DeploymentManager


def test_deploy_delegates_to_run_hop3_deploy(monkeypatch, tmp_path):
    mgr = DeploymentManager(
        host="1.2.3.4",
        config=DeploymentConfig(use_local_code=True, features=["mysql"]),
        repo_path=tmp_path,
    )
    captured: dict = {}

    def fake_run_hop3_deploy(**kwargs):
        captured.update(kwargs)
        if kwargs.get("on_output"):
            kwargs["on_output"]("deploying step 3 ...")
        return (True, 12.0)

    monkeypatch.setattr(depmod, "run_hop3_deploy", fake_run_hop3_deploy)
    monkeypatch.setattr(mgr, "_verify_installation", lambda _url: (True, ""))

    result = mgr.deploy()

    assert result.success is True
    # Reproduces the cloud invocation: `uv run hop3-deploy-server` from the checkout.
    assert captured["command_prefix"] == ["uv", "run"]
    assert str(captured["cwd"]) == str(tmp_path)
    assert captured["source"] == "local"  # use_local_code -> --from local
    assert "mysql" in captured["features"]
    assert captured["on_output"] is not None  # transcript captured for log_output
    assert "deploying step 3" in result.log_output


def test_deploy_uses_pypi_source_when_not_local(monkeypatch, tmp_path):
    mgr = DeploymentManager(
        host="1.2.3.4",
        config=DeploymentConfig(use_local_code=False),
        repo_path=tmp_path,
    )
    captured: dict = {}

    def fake_run_hop3_deploy(**kwargs):
        captured.update(kwargs)
        return (True, 1.0)

    monkeypatch.setattr(depmod, "run_hop3_deploy", fake_run_hop3_deploy)
    monkeypatch.setattr(mgr, "_verify_installation", lambda _url: (True, ""))

    mgr.deploy()
    assert captured["source"] == "pypi"


def test_deploy_failure_surfaces_error_and_transcript(monkeypatch, tmp_path):
    mgr = DeploymentManager(
        host="1.2.3.4", config=DeploymentConfig(), repo_path=tmp_path
    )

    def fake_run_hop3_deploy(**kwargs):
        if kwargs.get("on_output"):
            kwargs["on_output"]("apt-get install ... Error: held broken packages")
        return (False, 5.0)

    monkeypatch.setattr(depmod, "run_hop3_deploy", fake_run_hop3_deploy)

    result = mgr.deploy()
    assert result.success is False
    assert result.error  # a non-empty extracted error
    # The deploy transcript reaches log_output (not swallowed).
    assert "apt-get install" in result.log_output
