# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""RemoteTarget must forward every cloud-deploy option to run_hop3_deploy.

ADR 052 Phase 7b converges the two deploy wrappers onto RemoteTarget. Before the
cloud orchestrator is repointed at it (7b.5), RemoteTarget must carry everything
the cloud path needs: admin-domain/acme-email (or admin/ACME setup is silently
lost) and the uv-run/cwd invocation env (deploy from a source checkout).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hop3_testing.targets import remote as remote_mod
from hop3_testing.targets.config import DeploymentConfig, RemoteConfig
from hop3_testing.targets.remote import RemoteTarget


def test_remote_target_forwards_cloud_deploy_options(monkeypatch, tmp_path):
    captured: dict = {}

    def fake_run_hop3_deploy(**kwargs):
        captured.update(kwargs)
        return (False, 0.0)  # "failed" -> stops _deploy_and_connect before SSH

    monkeypatch.setattr(remote_mod, "run_hop3_deploy", fake_run_hop3_deploy)

    target = RemoteTarget(
        RemoteConfig(host="203.0.113.7", log_dir=tmp_path),
        deployment=DeploymentConfig(
            source="local",
            domain="admin.example.com",
            acme_email="ops@example.com",
            command_prefix=["uv", "run"],
            cwd=Path("/repo"),
        ),
    )
    # Failure path saves diagnostics; stub it so the test writes nothing.
    monkeypatch.setattr(target, "_save_diagnostics_on_error", lambda: None)

    with pytest.raises(RuntimeError):
        target.start()

    assert captured["domain"] == "admin.example.com"
    assert captured["acme_email"] == "ops@example.com"
    assert captured["command_prefix"] == ["uv", "run"]
    assert str(captured["cwd"]) == "/repo"


def test_run_path_emits_no_cloud_options(monkeypatch, tmp_path):
    # The plain `run` path leaves these unset -> None forwarded, nothing emitted.
    captured: dict = {}

    def fake_run_hop3_deploy(**kwargs):
        captured.update(kwargs)
        return (False, 0.0)

    monkeypatch.setattr(remote_mod, "run_hop3_deploy", fake_run_hop3_deploy)

    target = RemoteTarget(
        RemoteConfig(host="203.0.113.7", log_dir=tmp_path),
        deployment=DeploymentConfig(source="local"),
    )
    monkeypatch.setattr(target, "_save_diagnostics_on_error", lambda: None)

    with pytest.raises(RuntimeError):
        target.start()

    assert captured["domain"] is None
    assert captured["acme_email"] is None
    assert captured["command_prefix"] is None
    assert captured["cwd"] is None
