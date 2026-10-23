# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""`hop3-restore-server`: refuse without --yes, upload what is needed, run, report."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import TYPE_CHECKING

from hop3_installer.deployer.restore import (
    COMPONENTS,
    REMOTE_SCRIPT,
    SERVER_SCRIPT,
    main,
    remote_command,
    remote_snapshot_path,
    run_restore,
)

if TYPE_CHECKING:
    from pathlib import Path


class _Backend:
    def __init__(self, script_rc: int = 0):
        self.script_rc = script_rc
        self.config = SimpleNamespace(ssh_target="root@prod.test")
        self.uploads: list[tuple[Path, str]] = []
        self.dir_uploads: list[tuple[Path, str]] = []
        self.commands: list[str] = []
        self.streamed: list[str] = []

    def upload_file(self, local, remote):
        self.uploads.append((local, remote))
        return True

    def upload_dir(self, local, remote):
        self.dir_uploads.append((local, remote))
        return True

    def run(self, cmd, check=False):
        self.commands.append(cmd)
        return SimpleNamespace(success=True, stdout="", stderr="", returncode=0)

    def run_streaming(self, cmd):
        self.streamed.append(cmd)
        return self.script_rc


def test_the_server_script_ships_with_the_package():
    assert SERVER_SCRIPT.is_file()
    assert SERVER_SCRIPT.read_text().startswith("#!/bin/bash")


def test_a_bare_name_lives_under_the_backup_root():
    assert remote_snapshot_path("prod-pre-0.7.3") == "/var/backups/hop3/prod-pre-0.7.3"
    assert remote_snapshot_path("/srv/snap") == "/srv/snap"


def test_remote_command_always_passes_yes_and_quotes():
    cmd = remote_command(snapshot_dir="/var/backups/hop3/a b", only="db,config")
    assert cmd.startswith(REMOTE_SCRIPT)
    assert "'/var/backups/hop3/a b'" in cmd
    assert "--yes" in cmd
    assert "--only db,config" in cmd


def test_run_restore_uploads_the_script_then_runs_it():
    backend = _Backend()
    rc = run_restore(backend, snapshot="prod-pre-0.7.3", from_local=None, only=None)
    assert rc == 0
    assert backend.uploads == [(SERVER_SCRIPT, REMOTE_SCRIPT)]
    assert backend.streamed == [
        remote_command(snapshot_dir="/var/backups/hop3/prod-pre-0.7.3", only=None)
    ]


def test_a_local_snapshot_is_uploaded_first(tmp_path):
    (tmp_path / "SHA256SUMS").write_text("")
    backend = _Backend()
    rc = run_restore(backend, snapshot="prod-x", from_local=tmp_path, only=None)
    assert rc == 0
    assert backend.dir_uploads == [(tmp_path, "/var/backups/hop3/prod-x")]


def test_a_local_directory_without_checksums_is_refused(tmp_path):
    backend = _Backend()
    assert run_restore(backend, snapshot="x", from_local=tmp_path, only=None) == 1
    assert backend.streamed == []


def test_the_script_exit_code_is_the_exit_code(capsys):
    backend = _Backend(script_rc=1)
    assert run_restore(backend, snapshot="x", from_local=None, only=None) == 1
    assert "did not complete" in capsys.readouterr().out


def test_main_refuses_without_yes(capsys):
    assert main(["--host", "h", "--snapshot", "x"]) == 2
    assert "--yes" in capsys.readouterr().out


def test_only_offers_the_components_the_script_restores():
    """A component the script restores and `--only` does not name is unreachable."""
    script = SERVER_SCRIPT.read_text()
    restored = re.findall(r"^        ([\w-]+)\) has ", script, re.MULTILINE)
    assert restored == list(COMPONENTS)
    assert f"--only {','.join(COMPONENTS)}]" in script
