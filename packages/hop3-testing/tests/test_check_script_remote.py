# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
check.py runs ON the remote server, never silently auto-passed (audit C8).

On remote targets the runner used to fabricate a passed=True "skipped" result —
so check.py (the only app-specific body assertion) never ran and an app could go
green on a bare 200. It now uploads and executes check.py on the server and
fails loud when it can't.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from hop3_testing.runners.deployment import DeploymentTestRunner


class _FakeTarget:
    def __init__(self, *, exit_code: int = 0, raise_on: str | None = None) -> None:
        self.info = SimpleNamespace(http_base="http://remote.example:80")
        self._exit_code = exit_code
        self._raise_on = raise_on
        self.uploaded: tuple[str, str] | None = None
        self.exec_cmd: str | None = None

    def upload_file(self, local: Any, remote: str) -> None:
        if self._raise_on == "upload":
            msg = "sftp failed"
            raise OSError(msg)
        self.uploaded = (str(local), remote)

    def exec_run(self, cmd: str) -> tuple[int, str, str]:
        self.exec_cmd = cmd
        if self._raise_on == "exec":
            msg = "ssh exec failed"
            raise RuntimeError(msg)
        return self._exit_code, "stdout-body", ("boom" if self._exit_code else "")


def _session(tmp_path) -> Any:
    (tmp_path / "check.py").write_text("import sys\nsys.exit(0)\n")
    return SimpleNamespace(
        app_name="myapp",
        test_hostname="myapp.test.local",
        app=SimpleNamespace(path=tmp_path),
    )


def _run(target: Any, session: Any) -> tuple[str | None, list]:
    runner = DeploymentTestRunner(target=cast("Any", target), cleanup=True)
    results: list = []
    error = runner._run_check_script(cast("Any", session), results)
    return error, results


def test_remote_check_exit0_passes_on_server(tmp_path):
    target = _FakeTarget(exit_code=0)
    error, results = _run(target, _session(tmp_path))
    assert error is None
    assert results
    assert results[0].passed is True
    assert target.uploaded is not None  # actually ran on the server
    # The old silent auto-pass message must be gone.
    assert not any("skipped" in (r.message or "").lower() for r in results)


def test_remote_check_exit1_fails_loud(tmp_path):
    error, results = _run(_FakeTarget(exit_code=1), _session(tmp_path))
    assert error is not None
    assert "FAILED" in error
    assert results[0].passed is False


def test_remote_check_upload_failure_fails_loud(tmp_path):
    error, results = _run(_FakeTarget(raise_on="upload"), _session(tmp_path))
    assert error is not None
    assert "could not run on remote server" in error
    assert results[0].passed is False  # never a silent pass


def test_remote_check_runs_via_server_venv_python_not_uv(tmp_path):
    # Regression: `uv` isn't on the non-login SSH PATH (exit 127). check.py must
    # run with the hop3-server venv Python (which ships httpx), not `uv run`.
    target = _FakeTarget(exit_code=0)
    _run(target, _session(tmp_path))
    assert target.exec_cmd is not None
    assert target.exec_cmd.startswith("/home/hop3/venv/bin/python3 ")
    assert "uv run" not in target.exec_cmd
