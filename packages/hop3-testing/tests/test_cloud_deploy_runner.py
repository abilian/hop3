# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""The cloud deploy runner must not hang on a prompt, and must surface output.

A `hop3-test cloud` deploy runs `hop3-deploy-server` as a subprocess. If any
step prompts (ssh host-key on a freshly-rebuilt box, apt, sudo) and stdin is
inherited, it hangs the full 30-minute timeout with no output. Fix: stdin is
DEVNULL (EOF → fail fast), and on timeout the partial output is surfaced instead
of a blank "timed out".
"""

from __future__ import annotations

import subprocess

from hop3_testing.system_tests import deployment as depmod
from hop3_testing.system_tests.config import DeploymentConfig
from hop3_testing.system_tests.deployment import DeploymentManager


def test_deploy_runs_with_devnull_stdin(monkeypatch, tmp_path):
    mgr = DeploymentManager(
        host="1.2.3.4", config=DeploymentConfig(), repo_path=tmp_path
    )
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(depmod.subprocess, "run", _fake_run)
    monkeypatch.setattr(mgr, "_verify_installation", lambda _url: (True, None))

    mgr.deploy()
    assert captured.get("stdin") is subprocess.DEVNULL


def test_deploy_timeout_surfaces_partial_output(monkeypatch, tmp_path):
    mgr = DeploymentManager(
        host="1.2.3.4", config=DeploymentConfig(), repo_path=tmp_path
    )

    def _fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd, 1800, output="apt-get install ... [hung waiting for input]"
        )

    monkeypatch.setattr(depmod.subprocess, "run", _fake_run)

    result = mgr.deploy()
    assert result.success is False
    assert "timed out" in result.error.lower()
    # The partial output must reach the log, not vanish.
    assert "hung waiting for input" in result.log_output
