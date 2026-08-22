# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A worker's PATH must keep what the build artifact put there.

Regression: bugsink deploys two processes — gunicorn plus `bugsink-runsnappea`,
which drains its background queue. The web process survived because its command
is an absolute Nix store path; the worker's is a bare name, and the worker
builder was rebuilding PATH from a virtualenv shape and discarding the PATH the
spawner had assembled from the artifact's `path_prepend`. A Nix app keeps
nothing in `virtualenv_path`, so the name resolved nowhere:

    sh: 1: exec: bugsink-runsnappea: not found

uWSGI then respawn-throttled the daemon and the whole app was abandoned four
seconds in — reported as a startup failure with the web process running fine.
"""

from __future__ import annotations

import re

from hop3.run.uwsgi.worker import GenericWorker, WebWorker

NIX_BIN = "/nix/store/dzqf0kc-bugsink-2.1.2/venv/bin"


def _exported_path(kind: str, command: str, env: dict[str, str]) -> str:
    worker = (
        WebWorker("bugsink", command, env)
        if kind == "web"
        else GenericWorker("bugsink", command, env, kind=kind)
    )
    worker.update_settings()

    daemon = dict(worker.settings.values)["attach-daemon"]
    return re.search(r"export PATH=([^;\"]+)", daemon).group(1)


def test_worker_path_keeps_the_artifacts_directories() -> None:
    """The Nix store bin the toolchain established stays on PATH."""
    path = _exported_path(
        "snappea", "bugsink-runsnappea", {"PATH": f"{NIX_BIN}:/usr/bin"}
    )

    assert NIX_BIN in path.split(":")


def test_the_artifact_comes_before_the_system_directories() -> None:
    """The app's own binaries win over a same-named one in /usr/bin."""
    path = _exported_path(
        "snappea", "bugsink-runsnappea", {"PATH": f"{NIX_BIN}:/usr/bin"}
    ).split(":")

    assert path.index(NIX_BIN) < path.index("/usr/bin")


def test_the_web_worker_gets_the_same_path() -> None:
    """Both worker kinds run through one implementation, so neither can drift."""
    env = {"PATH": f"{NIX_BIN}:/usr/bin"}

    assert _exported_path("web", "gunicorn app:app", env) == _exported_path(
        "snappea", "bugsink-runsnappea", env
    )


def test_a_directory_is_not_repeated() -> None:
    """An entry the spawner already supplied is not appended a second time."""
    path = _exported_path("snappea", "cmd", {"PATH": "/usr/bin:/usr/local/bin"})

    assert path.split(":").count("/usr/bin") == 1


def test_no_path_from_the_spawner_still_yields_the_system_directories() -> None:
    """A toolchain that sets no paths must not produce an empty PATH."""
    path = _exported_path("snappea", "cmd", {}).split(":")

    assert "/usr/bin" in path
    assert "" not in path
