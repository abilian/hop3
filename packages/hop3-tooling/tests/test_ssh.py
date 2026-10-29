# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Every ssh the maintainer tools spawn: one builder, secrets off argv, no sudo."""

from __future__ import annotations

import io
import re
import subprocess
import tarfile
from pathlib import Path

import pytest
from hop3_tooling import cli, verify
from hop3_tooling.credentials import Credential
from hop3_tooling.ssh import ssh_argv

SRC = Path(__file__).parent.parent / "src" / "hop3_tooling"


class _FakeRun:
    """Records each subprocess call and answers with a canned stdout."""

    def __init__(self, stdout: str = "") -> None:
        self.calls: list[tuple[list[str], object]] = []
        self.stdout = stdout

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs.get("input")))
        return subprocess.CompletedProcess(argv, 0, self.stdout, "")


@pytest.fixture(autouse=True)
def _isolated_cli_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOP3_CONFIG_DIR", str(tmp_path / "cfg"))
    for var in ("HOP3_SSH_KEY", "HOP3_SSH_PORT", "HOP3_SSH_OPTIONS"):
        monkeypatch.delenv(var, raising=False)


def test_limesurvey_check_keeps_the_password_off_argv_and_uses_no_sudo(monkeypatch):
    fake = _FakeRun("USER=admin GEN=yes OLD=no\n")
    monkeypatch.setattr(verify.subprocess, "run", fake)
    cred = Credential(url="u", username="admin", email="e", password="s3cr3t-Pw")

    results = verify.limesurvey_db_check("box.example", "survey", cred)

    assert results == [
        ("old_default_rejected", True, "DB password_verify (SSH)"),
        ("generated_login_works", True, "DB user=admin (SSH)"),
    ]
    [(argv, script)] = fake.calls
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=accept-new" in argv
    assert not any("s3cr3t-Pw" in token for token in argv)
    assert isinstance(script, str)
    assert "export GEN=s3cr3t-Pw\n" in script
    assert "sudo" not in script
    assert "runuser -u hop3 -- php" in script


def test_remote_nix_build_copies_over_the_shared_ssh(monkeypatch, tmp_path):
    app = tmp_path / "myapp"
    app.mkdir()
    (app / "hop3.nix").write_text("{}")
    fake = _FakeRun()
    monkeypatch.setattr(cli.subprocess, "run", fake)

    cli._build_over_ssh(app, "box.example")

    assert [argv[0] for argv, _ in fake.calls] == ["ssh", "ssh", "ssh"]
    for argv, _ in fake.calls:
        assert "StrictHostKeyChecking=no" not in argv
        assert "root@box.example" in argv
    archive = fake.calls[0][1]
    assert isinstance(archive, bytes)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        assert "./hop3.nix" in tar.getnames()


def test_no_module_builds_its_own_ssh_command_line():
    """The tools reach ssh only through ``hop3_tooling.ssh``."""
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if path.name != "ssh.py"
        and re.search(
            r'\[\s*"(?:ssh|scp)"|StrictHostKeyChecking|\bsudo\b', path.read_text()
        )
    ]
    assert offenders == []


def test_the_operators_hop3_ssh_settings_do_not_reach_the_bench_boxes(
    monkeypatch,
):
    """
    `ssh_port = 2222` set for the operator's hop3 server sent every bench and
    verify connection to a freshly rebuilt box (listening on 22) to 2222.
    """
    monkeypatch.setenv("HOP3_SSH_PORT", "2222")
    monkeypatch.setenv("HOP3_SSH_KEY", "/home/op/.ssh/hop3_prod")
    monkeypatch.setenv("HOP3_SSH_OPTIONS", "ProxyJump=bastion")

    argv = ssh_argv("root@203.0.113.7", "true")

    assert "-p" not in argv
    assert "-i" not in argv
    assert "ProxyJump=bastion" not in argv
    assert argv[-2:] == ["root@203.0.113.7", "true"]


def test_a_target_can_still_name_its_own_port():
    argv = ssh_argv("root@203.0.113.7:2201", "true")
    assert argv[argv.index("-p") + 1] == "2201"
    assert "root@203.0.113.7" in argv
