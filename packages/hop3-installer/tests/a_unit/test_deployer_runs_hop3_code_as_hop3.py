# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The upgrade paths never run hop3's venv or checkout as root.

The venv and the checkout are hop3-writable, so root running their `pip`,
`python` or `git` (hooks, `core.fsmonitor`) runs code hop3 controls. The
version probes moved to hop3 while `pip install` still ran as root on all
three update paths.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hop3_installer.common import CommandResult
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer

HOP3_OWNED = ("/home/hop3/venv", "/home/hop3/hop3")


@pytest.mark.parametrize(
    "update",
    [
        lambda d: d._update_from_git(),
        lambda d: d._update_from_pypi(),
        lambda d: d._install_uploaded_code(Path("/nonexistent"), "/tmp/hop3-server"),
    ],
    ids=["git", "pypi", "local"],
)
def test_no_root_command_runs_hop3s_venv_or_checkout(update, monkeypatch) -> None:
    # Commands run on the target, and the revert hint the operator is told to
    # paste: both must go through hop3.
    commands: list[str] = []

    def run(cmd: str, **_kw) -> CommandResult:
        commands.append(cmd)
        return CommandResult(returncode=0, stdout="Version: 0.1\n", stderr="")

    def finish(revert: str, _msg: str) -> bool:
        commands.append(revert)
        return True

    backend = MagicMock()
    backend.run.side_effect = run
    backend.service_restart_command.return_value = "systemctl restart hop3-server"
    d = Deployer(DeployConfig(host="example.com", use_docker=False), backend)
    d.quiet = True
    monkeypatch.setattr(d, "_check_one_version", lambda _expected: True)
    monkeypatch.setattr(d, "_run_migrations", lambda: True)
    monkeypatch.setattr(d, "_package_version", lambda _pyproject: "0.1")
    monkeypatch.setattr(d, "_finish_upgrade", finish)

    assert update(d)

    touched = [c for c in commands if any(p in c for p in HOP3_OWNED)]
    assert touched, "the update ran nothing in hop3's venv or checkout"
    assert [c for c in touched if not c.startswith("su - hop3 -c ")] == []
