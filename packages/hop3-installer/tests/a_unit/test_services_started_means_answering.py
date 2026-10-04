# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
"Services started" means hop3-server answers, not that supervisord forked it.

The step reported success as soon as supervisord said RUNNING, seconds before
the server listened, and the CLI login that follows ran in that window: "Could
not connect", printed as a warning ahead of "Deployment complete!".
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer

# The package re-exports a `deploy` function that shadows the module name.
deploy_mod = sys.modules["hop3_installer.deployer.deploy"]


class _Backend:
    """supervisord starts at once; the server answers after ``ready_after`` probes."""

    def __init__(self, ready_after: int | None) -> None:
        self.ready_after = ready_after
        self.probes = 0

    def start_services(self) -> None:
        pass

    def run(self, cmd: str, **_kw) -> SimpleNamespace:
        self.probes += 1
        ready = self.ready_after is not None and self.probes > self.ready_after
        return SimpleNamespace(success=ready, stdout="", stderr="")


def _start(backend: _Backend, monkeypatch) -> bool:
    monkeypatch.setattr(deploy_mod.time, "sleep", lambda _s: None)
    deployer = Deployer(DeployConfig(use_docker=True), backend=backend)  # type: ignore[arg-type]
    success, _ = deployer._start_docker_services(0)
    return success


def test_the_step_waits_until_the_server_answers(monkeypatch):
    backend = _Backend(ready_after=3)

    assert _start(backend, monkeypatch)
    assert backend.probes == 4


def test_a_server_that_never_answers_fails_the_deploy(monkeypatch, capsys):
    assert not _start(_Backend(ready_after=None), monkeypatch)
    assert "did not answer" in capsys.readouterr().out
