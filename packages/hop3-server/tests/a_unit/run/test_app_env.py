# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The environment a one-off process gets inside an app is built from scratch.

The first `hop3 app shell` was deleted (2026-04-22) for leaking ``os.environ``,
the server's ``HOP3_SECRET_KEY`` included, into the child. ``build_app_env``
borrows ``PATH`` and nothing else, and follows ``make_env``'s precedence: the
build artifact's toolchain env and PATH first, the persisted ``[env]`` after,
never over a toolchain-owned key.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from hop3.core.artifacts import BuildArtifact, RuntimeConfig
from hop3.core.env import Env
from hop3.run.app_env import build_app_env, shell_session

APP_PATH = Path("/home/hop3/apps/myapp")


def _app(*, env: dict | None = None, port: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        name="myapp",
        app_path=APP_PATH,
        src_path=APP_PATH / "src",
        virtualenv_path=APP_PATH / "venv",
        home_path=APP_PATH / "home",
        tmp_path=APP_PATH / "tmp",
        port=port,
        get_runtime_env=lambda: Env(dict(env or {})),
    )


def _artifact(**runtime) -> BuildArtifact:
    return BuildArtifact(kind="nix", runtime=RuntimeConfig(**runtime))


# ---- build_app_env ----


def test_server_environment_never_leaks(monkeypatch) -> None:
    monkeypatch.setenv("HOP3_SECRET_KEY", "server-secret")
    monkeypatch.setenv("DATABASE_URL", "postgres://the-server-db")
    env = build_app_env(_app(), None)
    assert "HOP3_SECRET_KEY" not in env
    assert "DATABASE_URL" not in env


def test_home_and_tmpdir_are_the_apps_own() -> None:
    """
    Never the control plane's home. With it, every app shared one ``~/.ssh``:
    Gitea and Forgejo rewrote the ``authorized_keys`` holding Hop3's git-push
    keys, and every app's caches landed beside the server's own files.
    """
    env = build_app_env(_app(), None)
    assert env["HOME"] == f"{APP_PATH}/home"
    assert env["TMPDIR"] == f"{APP_PATH}/tmp"


def test_bootstrap_keys_and_venv_first_on_path(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = build_app_env(_app(), None)
    assert env["APP"] == "myapp"
    assert env["PATH"] == f"{APP_PATH}/venv/bin:/usr/bin:/bin"
    assert env["VIRTUAL_ENV"] == f"{APP_PATH}/venv"
    assert env["PWD"] == f"{APP_PATH}/src"


def test_artifact_toolchain_env_and_path_apply() -> None:
    artifact = _artifact(
        env_vars={"MIX_HOME": f"{APP_PATH}/.mix"},
        path_prepend=["/nix/store/abc-app/bin"],
    )
    env = build_app_env(_app(), artifact)
    assert env["MIX_HOME"] == f"{APP_PATH}/.mix"
    assert env["PATH"].startswith("/nix/store/abc-app/bin:")


def test_persisted_env_applies_but_never_over_a_toolchain_key() -> None:
    artifact = _artifact(env_vars={"MIX_HOME": f"{APP_PATH}/.mix"})
    app = _app(env={"MIX_HOME": "/home/hop3/apps/other/.mix", "API_KEY": "k"})
    env = build_app_env(app, artifact)
    assert env["MIX_HOME"] == f"{APP_PATH}/.mix"
    assert env["API_KEY"] == "k"


def test_port_follows_the_app() -> None:
    assert build_app_env(_app(port=5000), None)["PORT"] == "5000"
    assert "PORT" not in build_app_env(_app(), None)


# ---- shell_session ----


def test_session_defaults_to_the_source_tree_and_bash_without_rc() -> None:
    session = shell_session(_app(), None, shell="/bin/bash", term="xterm-256color")
    assert session.argv == ("/bin/bash", "--norc")
    assert session.cwd == APP_PATH / "src"
    assert session.env["PWD"] == str(session.cwd)
    assert session.env["TERM"] == "xterm-256color"
    assert "myapp" in session.env["PS1"]
    assert session.env["HISTFILE"] == ""


def test_session_runs_from_the_artifact_working_dir() -> None:
    artifact = _artifact(working_dir="/nix/store/abc-app/lib/app")
    session = shell_session(_app(), artifact, shell="/bin/sh", term=None)
    assert session.cwd == Path("/nix/store/abc-app/lib/app")
    assert session.env["PWD"] == "/nix/store/abc-app/lib/app"
    assert session.argv == ("/bin/sh",)
    assert "TERM" not in session.env


def test_session_drops_the_forced_command_variables(monkeypatch) -> None:
    monkeypatch.setenv("FINGERPRINT", "SHA256:abc")
    monkeypatch.setenv("NAME", "default")
    session = shell_session(_app(), None, shell="/bin/bash", term=None)
    assert "FINGERPRINT" not in session.env
    assert "NAME" not in session.env
