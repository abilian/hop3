# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The deployer never acts as root on a path the hop3 user controls.

Everything under /home/hop3 is hop3-writable, and apps run as hop3: root
running the venv's `pip` or `python` runs code hop3 controls, and root writing,
`chmod`ing or `chown`ing a file there follows a symlink an app planted. The
version probes moved to hop3 while `pip install` still ran as root on all
three update paths, and the admin-domain edit, the build-info manifest and the
self-signed certificate stayed root's.

One exception, deliberate: `_reclaim_venv` chowns the venv back to hop3 as
root, with `-P -h` so no symlink is followed. hop3-rootd, which runs as root,
is no exception: it lives in a venv root owns (`/opt/hop3-rootd`), installed
there by the installer's `--rootd` mode, never by pip in hop3's venv.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hop3_installer.common import CommandResult
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer

HOP3_HOME = "/home/hop3"
AS_HOP3 = "su - hop3 -c "

#: The installer itself is not uploaded; its runs are recorded.
pytestmark = pytest.mark.usefixtures("installer_runs_recorded")


def _deployer(monkeypatch, commands: list[str], **config) -> Deployer:
    def run(cmd: str, **_kw) -> CommandResult:
        commands.append(cmd)
        return CommandResult(returncode=0, stdout="Version: 0.1\n", stderr="")

    def finish(revert: str, _msg: str) -> bool:
        # The revert hint the operator is told to paste counts too.
        commands.append(revert)
        return True

    backend = MagicMock()
    backend.run.side_effect = run
    backend.service_restart_command.return_value = "systemctl restart hop3-server"
    d = Deployer(DeployConfig(host="example.com", use_docker=False, **config), backend)
    d.quiet = True
    monkeypatch.setattr(d, "_check_one_version", lambda _expected: True)
    monkeypatch.setattr(d, "_run_migrations", lambda: True)
    monkeypatch.setattr(d, "_package_version", lambda _pyproject: "0.1")
    monkeypatch.setattr(d, "_finish_upgrade", finish)
    monkeypatch.setattr(d, "_restart_and_verify", lambda *_a: True)
    monkeypatch.setattr(d, "_update_nginx_for_ssl", lambda *_a: True)
    return d


@pytest.mark.parametrize(
    "step",
    [
        lambda d: d._update_from_git(),
        lambda d: d._update_from_pypi(),
        lambda d: d._install_uploaded_code(Path("/nonexistent"), "/tmp/hop3-server"),
        lambda d: d._persist_admin_domain("admin.example.com"),
        lambda d: d._generate_self_signed_cert(
            "admin.example.com", "/home/hop3/ssl/admin.example.com"
        ),
    ],
    ids=["git", "pypi", "local", "admin-domain", "self-signed-cert"],
)
def test_no_root_command_touches_hop3s_home(step, monkeypatch) -> None:
    commands: list[str] = []
    d = _deployer(monkeypatch, commands)

    assert step(d)

    touched = [c for c in commands if HOP3_HOME in c]
    assert touched, "the step ran nothing under hop3's home"
    assert [c for c in touched if not c.startswith(AS_HOP3)] == []


def test_the_build_info_is_written_by_hop3_from_stdin(monkeypatch) -> None:
    calls: list[tuple[str, str | None]] = []

    def run(cmd: str, *, check: bool = True, stdin: str | None = None):
        calls.append((cmd, stdin))
        return CommandResult(returncode=0, stdout="", stderr="")

    backend = MagicMock()
    backend.run.side_effect = run
    d = Deployer(DeployConfig(host="example.com", use_docker=False), backend)
    d.quiet = True
    monkeypatch.setattr(d, "_deploy_method", lambda: "pypi")
    monkeypatch.setattr(d, "_server_installed_version", lambda: "0.1")

    d._write_build_info()

    writes = [(c, s) for c, s in calls if "build-info" in c]
    assert len(writes) == 1
    command, stdin = writes[0]
    assert command.startswith(AS_HOP3)
    assert "chown" not in command
    assert stdin is not None
    assert '"version": "0.1"' in stdin


def test_a_git_update_installs_the_branch_the_way_the_installer_does(
    monkeypatch,
) -> None:
    """No checkout on the server: pip fetches each package from the repository."""
    commands: list[str] = []
    d = _deployer(monkeypatch, commands)
    d.config.branch = "devel"

    assert d._update_from_git()

    install = next(c for c in commands if "install" in c)
    for subdir in ("hop3-server", "hop3-cli"):
        assert f"@devel#subdirectory=packages/{subdir}" in install
    assert "git+https://github.com/abilian/hop3.git" in install
    assert not [c for c in commands if "/home/hop3/hop3 " in c or "git -C" in c]


@pytest.mark.parametrize(
    ("config", "step", "source"),
    [
        (
            {"use_git": True, "branch": "devel"},
            "_update_from_git",
            " --from git --branch devel",
        ),
        ({"pypi_version": "0.8.1"}, "_update_from_pypi", " --version 0.8.1"),
        ({}, "local", " --path /tmp/hop3-server"),
    ],
    ids=["git", "pypi", "local"],
)
def test_rootd_goes_into_its_own_venv_by_the_installer(
    config, step, source, monkeypatch, installer_runs_recorded
) -> None:
    """Every update path: never pip in hop3's venv, always the installer as root."""
    commands: list[str] = []
    d = _deployer(monkeypatch, commands, **config)

    if step == "local":
        assert d._install_uploaded_code(Path("/nonexistent"), "/tmp/hop3-server")
    else:
        assert getattr(d, step)()

    assert installer_runs_recorded == [f" --rootd{source} --verbose"]
    # Up to the first `&&`: a revert hint chains the root half after it.
    hop3_pip = [
        c.split(" && ")[0] for c in commands if c.startswith(AS_HOP3) and "pip" in c
    ]
    assert hop3_pip
    assert not [c for c in hop3_pip if "hop3-rootd" in c]


def test_the_revert_hint_reinstalls_rootd_as_root_into_its_venv(monkeypatch) -> None:
    commands: list[str] = []
    d = _deployer(monkeypatch, commands, pypi_version="0.8.1")

    assert d._update_from_pypi()

    revert = commands[-1]
    assert "/opt/hop3-rootd/bin/pip install hop3-rootd==0.1" in revert
    hop3_part = revert.split(" && ")[0]
    assert hop3_part.startswith(AS_HOP3)
    assert "hop3-rootd" not in hop3_part


def test_the_venv_is_reclaimed_without_following_symlinks(monkeypatch) -> None:
    """Root pip runs of older deployers left root-owned files in the venv."""
    commands: list[str] = []
    d = _deployer(monkeypatch, commands)

    assert d._reclaim_venv()

    assert commands == ["chown -R -P -h hop3:hop3 /home/hop3/venv"]


def test_a_failed_stale_metadata_removal_stops_the_install(monkeypatch) -> None:
    backend = MagicMock()
    backend.run.return_value = CommandResult(
        returncode=1, stdout="", stderr="Permission denied"
    )
    d = Deployer(DeployConfig(host="example.com", use_docker=False), backend)
    d.quiet = True

    assert not d._install_uploaded_code(Path("/nonexistent"), "/tmp/hop3-server")
    assert backend.run.call_count == 1  # nothing installed after it
