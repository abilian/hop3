# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""`hop3-backup-server`: upload the bundled script, run it under a label, fetch."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from hop3_installer.deployer.backup import (
    REMOTE_SCRIPT,
    SERVER_SCRIPT,
    build_parser,
    infer_label,
    remote_command,
    run_backup,
)

if TYPE_CHECKING:
    from pathlib import Path


class _Backend:
    """Records what the command asks of the server; ``script_rc`` is its exit."""

    def __init__(self, script_rc: int = 0, fetch_ok: bool = True):
        self.script_rc = script_rc
        self.fetch_ok = fetch_ok
        self.config = SimpleNamespace(ssh_target="root@prod.test")
        self.uploads: list[tuple[Path, str]] = []
        self.commands: list[str] = []
        self.streamed: list[str] = []
        self.downloads: list[tuple[str, Path]] = []

    def upload_file(self, local, remote):
        self.uploads.append((local, remote))
        return True

    def run(self, cmd, check=False):
        self.commands.append(cmd)
        stdout = "prod\n" if cmd == "hostname -s" else ""
        return SimpleNamespace(success=True, stdout=stdout, stderr="", returncode=0)

    def run_streaming(self, cmd):
        self.streamed.append(cmd)
        return self.script_rc

    def download_dir(self, remote, local):
        self.downloads.append((remote, local))
        return self.fetch_ok


def test_the_server_script_ships_with_the_package():
    assert SERVER_SCRIPT.is_file()
    assert SERVER_SCRIPT.read_text().startswith("#!/bin/bash")


def test_label_is_the_version_when_given():
    assert infer_label(None, "0.7.3") == "pre-0.7.3"
    assert infer_label("weekly", "0.7.3") == "weekly"
    assert infer_label(None, None).isdigit() or "-" in infer_label(None, None)


def test_remote_command_quotes_and_forwards_flags():
    cmd = remote_command(
        label="pre 0.7.3",
        dest="/var/backups/hop3/x",
        skip_apps=True,
        docker_volumes=False,
    )
    assert cmd.startswith(REMOTE_SCRIPT)
    assert "'pre 0.7.3'" in cmd
    assert "--skip-apps" in cmd
    assert "--docker-volumes" not in cmd


def test_run_backup_uploads_runs_and_names_the_snapshot(capsys, tmp_path):
    backend = _Backend()
    rc = run_backup(
        backend,
        label="pre-0.7.3",
        dest=None,
        skip_apps=False,
        docker_volumes=False,
        fetch=None,
    )
    assert rc == 0
    assert backend.uploads == [(SERVER_SCRIPT, REMOTE_SCRIPT)]
    assert backend.commands[0].startswith("chmod 0755")
    assert backend.streamed == [
        remote_command(
            label="pre-0.7.3",
            dest="/var/backups/hop3/prod-pre-0.7.3",
            skip_apps=False,
            docker_volumes=False,
        )
    ]
    assert "/var/backups/hop3/prod-pre-0.7.3" in capsys.readouterr().out
    assert backend.downloads == []


def test_run_backup_fetches_into_the_given_directory(tmp_path):
    backend = _Backend()
    rc = run_backup(
        backend,
        label="pre-0.7.3",
        dest="/srv/snap",
        skip_apps=True,
        docker_volumes=False,
        fetch=tmp_path,
    )
    assert rc == 0
    assert backend.downloads == [("/srv/snap", tmp_path / "snap")]


def test_a_failed_script_is_the_exit_code_and_nothing_is_fetched(tmp_path, capsys):
    backend = _Backend(script_rc=3)
    rc = run_backup(
        backend,
        label="x",
        dest=None,
        skip_apps=False,
        docker_volumes=False,
        fetch=tmp_path,
    )
    assert rc == 3
    assert backend.downloads == []
    assert "did not complete" in capsys.readouterr().out


def test_parser_defaults():
    args = build_parser().parse_args(["--host", "h", "--version", "0.7.3"])
    assert (args.ssh_user, args.port, args.ssh_key, args.fetch) == (
        "root",
        22,
        None,
        None,
    )
    assert infer_label(args.label, args.version) == "pre-0.7.3"
