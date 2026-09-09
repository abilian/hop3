# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
An in-place update leaves one version of Hop3 on the box, and proves it.

Found while rehearsing a 0.6.2 to 0.7.3 upgrade (2026-09-09): every update
path installed hop3-server alone, so rootd and the client stayed at the old
version beside the new server; and a Docker upload that merged into the old
tree had pip reinstall the old server under a "Local code deployed" message.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from hop3_installer.deployer.backends.base import DeployBackend
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_a: None)


class _Box:
    """Records commands; answers the version probe from ``versions``."""

    def __init__(self, versions: dict[str, str]):
        self.versions = versions
        self.commands: list[str] = []

    def run(self, cmd, check=False):
        self.commands.append(cmd)
        stdout = ""
        if "importlib.metadata" in cmd:
            stdout = "".join(f"{k} {v}\n" for k, v in self.versions.items())
        elif "pip show hop3-server" in cmd:
            stdout = "Name: hop3-server\nVersion: 0.6.2\n"
        elif "grep -m1 '^version'" in cmd:
            stdout = 'version = "0.7.3"\n'
        return SimpleNamespace(success=True, stdout=stdout, stderr="", returncode=0)

    def upload_dir(self, local_path, remote_path):
        self.commands.append(f"upload {remote_path}")
        return True

    service_restart_command = DeployBackend.service_restart_command
    service_logs_command = DeployBackend.service_logs_command
    restart_service = DeployBackend.restart_service


ONE_VERSION = {"hop3_server": "0.7.3", "hop3_rootd": "0.7.3", "hop3_cli": "0.7.3"}


def _deployer(box, tmp_path, **config):
    # A local checkout with the three packages, hop3-server at 0.7.3.
    for pkg in ("hop3-server", "hop3-rootd", "hop3-cli"):
        d = tmp_path / "packages" / pkg
        d.mkdir(parents=True)
        (d / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.7.3"\n')
    cfg = DeployConfig(host="example.com", project_root=tmp_path, **config)
    return Deployer(cfg, backend=box)  # type: ignore[arg-type]


def test_local_update_installs_all_three_and_checks_them(tmp_path):
    box = _Box(ONE_VERSION)
    assert _deployer(box, tmp_path, use_local_code=True)._update_local_code() is True
    installs = [c for c in box.commands if "pip install" in c]
    assert any("/tmp/hop3-server" in c for c in installs)
    assert any("/tmp/hop3-rootd /tmp/hop3-cli" in c for c in installs)
    probe = next(i for i, c in enumerate(box.commands) if "importlib.metadata" in c)
    migrate = next(i for i, c in enumerate(box.commands) if "db:upgrade" in c)
    assert probe < migrate, "the version check runs before the migration"


def test_pinned_pypi_update_pins_all_three(tmp_path):
    box = _Box(ONE_VERSION)
    assert _deployer(box, tmp_path, pypi_version="0.7.3")._update_from_pypi() is True
    install = next(c for c in box.commands if "pip install --upgrade" in c)
    for pkg in ("hop3-server==0.7.3", "hop3-rootd==0.7.3", "hop3-cli==0.7.3"):
        assert pkg in install


def test_a_daemon_left_behind_fails_before_the_migration(tmp_path, capsys):
    box = _Box({**ONE_VERSION, "hop3_rootd": "0.6.2"})
    assert _deployer(box, tmp_path, pypi_version="0.7.3")._update_from_pypi() is False
    assert not any("db:upgrade" in c for c in box.commands)
    assert not any("restart" in c for c in box.commands)
    assert "hop3-rootd: 0.6.2" in capsys.readouterr().out


def test_the_old_server_reinstalled_fails_loud(tmp_path, capsys):
    # The Docker upload that merged into the old tree: pip "succeeded" at 0.6.2.
    box = _Box(dict.fromkeys(ONE_VERSION, "0.6.2"))
    assert _deployer(box, tmp_path, use_local_code=True)._update_local_code() is False
    assert "expected: 0.7.3" in capsys.readouterr().out


def test_rootd_restarts_before_the_server(tmp_path):
    box = _Box(ONE_VERSION)
    assert _deployer(box, tmp_path, pypi_version="0.7.3")._update_from_pypi() is True
    rootd = next(i for i, c in enumerate(box.commands) if "restart hop3-rootd" in c)
    server = next(i for i, c in enumerate(box.commands) if "restart hop3-server" in c)
    assert rootd < server
