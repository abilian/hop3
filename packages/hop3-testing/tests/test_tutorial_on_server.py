# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Tutorials run ON a remote server, not locally (so deploys hit the run target).

The dispatch keys off the target's class name being "RemoteTarget" plus a
``tutorial_token`` placed by ``ensure_tutorial_host``. A remote target without a
token must error — never fall back to local execution, which would deploy to the
dev machine's default CLI context (the wrong server).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from hop3_testing.runners.tutorial import TutorialTestRunner
from hop3_testing.targets.config import RemoteConfig
from hop3_testing.targets.remote import RemoteTarget as RealRemoteTarget


class RemoteTarget:
    """A stand-in whose class name matches the real RemoteTarget."""

    def __init__(self, token=None):
        self.info = SimpleNamespace(ssh_host="1.2.3.4")
        self.tutorial_token = token
        self.calls: list = []
        self.uploaded: list = []

    def exec_run(self, cmd):
        self.calls.append(cmd)
        return (0, "ok", "")

    def upload_file(self, local, remote):
        self.uploaded.append((str(local), remote))


def test_remote_without_token_errors_and_never_runs_locally():
    target = RemoteTarget(token=None)
    target.tutorial_host_error = "validoc install failed"
    runner = TutorialTestRunner(target=target)

    result = runner._run_validoc(Path("/x/flask.md"), Path("/x"))

    assert result["success"] is False
    assert "not prepared" in result["error"]
    assert "validoc install failed" in result["error"]
    assert target.uploaded == []  # nothing uploaded, nothing executed remotely
    assert target.calls == []


def test_remote_with_token_runs_validoc_on_the_server():
    token = "eyJ" + "a" * 30 + ".eyJ" + "b" * 30 + "." + "c" * 30
    target = RemoteTarget(token=token)
    runner = TutorialTestRunner(target=target)

    result = runner._run_validoc(Path("/x/flask.md"), Path("/x"))

    assert result["success"] is True
    # the markdown is uploaded under a scratch dir, named after the tutorial
    assert target.uploaded[0][1].startswith("/tmp/hop3-tut/")
    assert target.uploaded[0][1].endswith("/flask.md")
    # validoc is invoked on the server, pointed at the local server with the token
    run_cmds = [c for c in target.calls if isinstance(c, str) and "validoc run" in c]
    assert run_cmds, "validoc was not run on the server"
    cmd = run_cmds[0]
    assert "/home/hop3/venv/bin/validoc run" in cmd
    assert "HOP3_API_URL=http://localhost:8000" in cmd
    assert token in cmd
    assert "HOP3_NO_INPUT=1" in cmd
    # the scratch dir is cleaned up
    assert any(isinstance(c, list) and c[:2] == ["rm", "-rf"] for c in target.calls)


def test_non_remote_target_uses_the_local_path(monkeypatch):
    class DockerTarget:
        info = SimpleNamespace(ssh_host="local")

    runner = TutorialTestRunner(target=DockerTarget())
    # The runner is a frozen dataclass; patch the method on the class.
    monkeypatch.setattr(
        TutorialTestRunner,
        "_run_validoc_local",
        lambda self, p, c: {"success": True, "logs": "local"},
    )

    result = runner._run_validoc(Path("/x/flask.md"), Path("/x"))

    assert result["logs"] == "local"


def test_upload_file_sftps_and_makes_parent_dir(monkeypatch):
    rt = RealRemoteTarget(RemoteConfig(host="h"))
    sftp = MagicMock()
    client = MagicMock()
    client.open_sftp.return_value = sftp
    rt._ssh_client = client
    mkdirs: list = []
    monkeypatch.setattr(rt, "exec_run", lambda cmd: mkdirs.append(cmd) or (0, "", ""))

    rt.upload_file("/local/flask.md", "/tmp/hop3-tut/flask/flask.md")

    assert ["mkdir", "-p", "/tmp/hop3-tut/flask"] in mkdirs
    sftp.put.assert_called_once_with("/local/flask.md", "/tmp/hop3-tut/flask/flask.md")
    sftp.close.assert_called_once()
