# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""SSHDeployBackend.setup() surfaces the real failure reason (fail loud).

A bare ``False`` hid why "Setting up deployment target" failed — most often a
changed host key on a rebuilt target (StrictHostKeyChecking=accept-new refuses it).
The reason must be printed so it reaches the deploy output / build detail.
"""

from __future__ import annotations

from hop3_installer.common import CommandResult
from hop3_installer.deployer.backends.ssh import SSHDeployBackend
from hop3_installer.deployer.config import DeployConfig


def test_setup_failure_prints_the_real_ssh_error(capsys, monkeypatch):
    backend = SSHDeployBackend(DeployConfig(host="198.51.100.9"))
    # The connectivity check fails with a host-key error (the rebuild heisenbug).
    monkeypatch.setattr(
        backend,
        "run",
        lambda *a, **k: CommandResult(
            returncode=255, stderr="Host key verification failed."
        ),
    )

    assert backend.setup() is False
    out = capsys.readouterr().out
    assert "Host key verification failed." in out  # the real cause, not a bare False
    assert "198.51.100.9" in out


def test_setup_succeeds_when_checks_pass(monkeypatch):
    backend = SSHDeployBackend(DeployConfig(host="198.51.100.9"))
    monkeypatch.setattr(backend, "run", lambda *a, **k: CommandResult(returncode=0))
    assert backend.setup() is True
