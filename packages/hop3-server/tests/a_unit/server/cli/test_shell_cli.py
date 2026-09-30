# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""``hop3-server app-shell``: refuses loudly, or execs the session and nothing else."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from hop3.core.env import Env
from hop3.server.cli import shell as shell_cli
from hop3.server.cli.shell import AppShellExecCmd


def _app(tmp_path: Path, *, runtime: str = "uwsgi", deployed: bool = True):
    app_path = tmp_path / "apps" / "myapp"
    (app_path / "src" if deployed else app_path).mkdir(parents=True)
    return SimpleNamespace(
        name="myapp",
        runtime=runtime,
        app_path=app_path,
        src_path=app_path / "src",
        virtualenv_path=app_path / "venv",
        home_path=app_path / "home",
        tmp_path=app_path / "tmp",
        port=0,
        get_runtime_env=lambda: Env({}),
    )


@pytest.fixture
def lookup(monkeypatch):
    """Stand in for the database: the command finds whatever ``lookup.app`` is."""
    holder = SimpleNamespace(app=None)
    monkeypatch.setattr(shell_cli, "get_session_factory", MagicMock)
    monkeypatch.setattr(
        shell_cli,
        "AppRepository",
        lambda session: SimpleNamespace(get_one_or_none=lambda name: holder.app),
    )
    return holder


def _refused(name: str, capsys) -> str:
    with pytest.raises(SystemExit) as exc:
        AppShellExecCmd().run(app_name=name)
    assert exc.value.code == 1
    return capsys.readouterr().err


def test_command_name() -> None:
    assert AppShellExecCmd().name == "app-shell"


def test_refuses_an_invalid_name_before_touching_the_db(lookup, capsys) -> None:
    assert "app-shell:" in _refused("../etc", capsys)


def test_refuses_an_unknown_app(lookup, capsys) -> None:
    assert "no app named 'ghost'" in _refused("ghost", capsys)


def test_refuses_a_docker_compose_app(lookup, tmp_path, capsys) -> None:
    lookup.app = _app(tmp_path, runtime="docker-compose")
    assert "docker-compose" in _refused("myapp", capsys)


def test_refuses_an_app_that_was_never_deployed(lookup, tmp_path, capsys) -> None:
    lookup.app = _app(tmp_path, deployed=False)
    assert "deploy it first" in _refused("myapp", capsys)


def test_execs_the_session_in_the_app_context(lookup, tmp_path, monkeypatch) -> None:
    lookup.app = _app(tmp_path)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("HOP3_SECRET_KEY", "server-secret")
    monkeypatch.setattr(shell_cli, "_pick_shell", lambda: "/bin/bash")
    seen: dict = {}
    monkeypatch.setattr(os, "chdir", lambda path: seen.__setitem__("cwd", Path(path)))
    monkeypatch.setattr(
        os,
        "execve",
        lambda path, argv, env: seen.update(path=path, argv=argv, env=env),
    )

    AppShellExecCmd().run(app_name="myapp")

    assert seen["cwd"] == lookup.app.src_path
    assert seen["path"] == "/bin/bash"
    assert seen["argv"] == ("/bin/bash", "--norc")
    assert seen["env"]["APP"] == "myapp"
    assert seen["env"]["TERM"] == "xterm"
    assert "HOP3_SECRET_KEY" not in seen["env"]
