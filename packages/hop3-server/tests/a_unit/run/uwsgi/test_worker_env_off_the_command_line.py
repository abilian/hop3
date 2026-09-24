# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A worker's environment never travels on a command line.

Regression: every ``attach-daemon`` worker was started as
``sh -c "cd src && export SECRET_KEY='…'; …; exec cmd"``, and uWSGI keeps
that ``sh -c`` alive as the daemon's parent. ``/proc/<pid>/cmdline`` is
readable by every local user, so ``ps`` showed every app's database password
and secret key to ``www-data``, ``postgres`` and every other app. The
environment now goes to a file only its owner can read, and the command line
names the file.
"""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from hop3 import config as c
from hop3.config import HopConfig
from hop3.run.uwsgi import worker as worker_module
from hop3.run.uwsgi.worker import GenericWorker

if TYPE_CHECKING:
    from pathlib import Path

SECRET = "s3cr3t-do-not-print"


@pytest.fixture
def hop3_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOP3_ROOT", str(tmp_path))
    HopConfig.reset_instance()
    for name in ("UWSGI_AVAILABLE", "UWSGI_ENABLED"):
        directory = tmp_path / name.lower()
        directory.mkdir()
        monkeypatch.setattr(c, name, directory)
    yield tmp_path
    HopConfig.reset_instance()


def _worker() -> GenericWorker:
    worker = GenericWorker(
        "myapp", "serve --port $PORT", {"SECRET_KEY": SECRET}, kind="worker"
    )
    worker.update_settings()
    return worker


def test_no_env_value_reaches_the_command_line() -> None:
    worker = _worker()
    line = dict(worker.settings.values)["attach-daemon"]

    assert SECRET not in line
    assert "export" not in line
    assert f". {worker.env_file} && exec serve --port $PORT" in line


def test_the_env_file_is_private(hop3_root: Path) -> None:
    worker = _worker()
    worker.write_settings()

    assert worker.env_file.is_relative_to(hop3_root)
    assert SECRET in worker.env_file.read_text()
    assert stat.S_IMODE(worker.env_file.stat().st_mode) == 0o600


def test_the_env_file_exists_before_the_vassal_is_enabled(
    hop3_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The vassal starts when its .ini is copied into UWSGI_ENABLED."""
    worker = _worker()
    seen: list[bool] = []
    real_copy = worker_module.shutil.copyfile

    def copy_and_check(src: Path, dst: Path) -> Path:
        seen.append(worker.env_file.exists())
        return real_copy(src, dst)

    monkeypatch.setattr(worker_module.shutil, "copyfile", copy_and_check)
    worker.write_settings()

    assert seen == [True]
