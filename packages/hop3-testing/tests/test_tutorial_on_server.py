# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Tutorials run on the target, a container included, so deploys hit the run target.

``tutorial_host_problem`` is cleared once ``ensure_tutorial_host`` succeeded. A
target that was not prepared must error. Running locally instead would deploy
to the dev machine's default CLI context, which may be another server.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from hop3_testing.runners.tutorial import TutorialTestRunner
from hop3_testing.targets.base import TargetInfo
from hop3_testing.targets.config import RemoteConfig
from hop3_testing.targets.remote import RemoteTarget as RealRemoteTarget


class RemoteTarget:
    """A stand-in whose class name matches the real RemoteTarget."""

    def __init__(self, *, ready: bool):
        self.info = TargetInfo(ssh_host="1.2.3.4", ssh_port=22)
        self.tutorial_host_problem = None if ready else "not prepared for tutorials"
        self.calls: list = []
        self.uploaded: list = []

    def exec_run(self, cmd, **_kw):
        self.calls.append(cmd)
        return (0, "ok", "")

    def upload_file(self, local, remote):
        self.uploaded.append((str(local), remote))


def test_unprepared_remote_errors_and_never_runs_locally():
    target = RemoteTarget(ready=False)
    target.tutorial_host_problem = "validoc install failed"
    runner = TutorialTestRunner(target=target)

    result = runner._run_validoc(Path("/x/flask.md"))

    assert result["success"] is False
    assert "not prepared" in result["error"]
    assert "validoc install failed" in result["error"]
    assert target.uploaded == []  # nothing uploaded, nothing executed remotely
    assert target.calls == []


def test_prepared_remote_runs_validoc_on_the_server():
    target = RemoteTarget(ready=True)
    runner = TutorialTestRunner(target=target)

    result = runner._run_validoc(Path("/x/flask.md"))

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
    # the token is read from the server's file, never written on the line
    assert 'HOP3_API_TOKEN="$(cat /home/hop3/.hop3-harness-admin-token)"' in cmd
    assert "eyJ" not in cmd
    # curl accepts the test server's self-signed certificate via CURL_HOME
    assert "CURL_HOME=/tmp/hop3-tut/flask" in cmd
    assert any(isinstance(c, str) and ".curlrc" in c for c in target.calls)
    assert "HOP3_NO_INPUT=1" in cmd
    assert "HOP3_TEST_DOMAIN=1.2.3.4.sslip.io" in cmd
    # the scratch dir is cleaned up
    assert any(isinstance(c, list) and c[:2] == ["rm", "-rf"] for c in target.calls)


def test_a_container_runs_tutorials_inside_it_against_loopback():
    """
    validoc ran on the developer's machine for a Docker target: it needed every
    toolchain there, and its curl reached the Docker host's port 443 instead of
    the container's nginx.
    """
    target = RemoteTarget(ready=True)
    target.info = TargetInfo(
        ssh_host="hop3@fedora.local", ssh_port=32768, is_container=True
    )
    runner = TutorialTestRunner(target=target)

    result = runner._run_validoc(Path("/x/flask.md"))

    assert result["success"] is True
    cmd = next(c for c in target.calls if isinstance(c, str) and "validoc run" in c)
    assert "HOP3_TEST_DOMAIN=127.0.0.1.sslip.io" in cmd


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
