# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A Python app's `[build].build` runs inside the app's virtualenv.

Regression test. Making the Python toolchain honour `[build].build` (it had
silently ignored it) exposed a second defect the first one had been hiding: the
declared command ran with the ambient environment, so a recipe saying
`pip install -r requirements.txt` got the *system* pip. On a fresh Ubuntu 24.04
that Python is marked externally managed (PEP 668) and pip refuses, advising the
operator to create a virtualenv — the one Hop3 had just created and then failed
to use. Three of the four native Python apps in the benchmark corpus failed this
way on the 2026-07-28 run, in a build lasting seconds, while the fourth (which
declares no build command) passed.

So the assertion is about the environment, not about whether the hook fires:
that is `test_declared_build_conformance.py`'s job.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from hop3.toolchains.python import PythonToolchain

if TYPE_CHECKING:
    from pathlib import Path


class _Recorder(PythonToolchain):
    """A toolchain that records the environment its shell calls receive."""

    def __init__(self, venv: Path, command: str) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self._venv = venv
        self._command = command
        self.app_name = "some-app"

    @property
    def virtual_env(self) -> Path:
        return self._venv

    def _get_custom_build_command(self) -> str | None:
        return self._command

    def shell(self, command, cwd="", *, env=None, check=True):  # type: ignore[override]
        self.calls.append((command, env))


def test_declared_build_runs_with_the_venv_on_path(tmp_path: Path) -> None:
    """Bare `pip` in a declared build must resolve to the app's venv."""
    venv = tmp_path / "venv"
    toolchain = _Recorder(venv, "pip install -r requirements.txt")

    assert toolchain._run_declared_build(env=toolchain._venv_env()) is True

    command, env = toolchain.calls[0]
    assert command == "pip install -r requirements.txt"
    assert env is not None, "the declared build must not inherit the ambient env"

    # The venv's bin must come FIRST: a system pip earlier on PATH is exactly
    # the failure this guards against.
    first_entry = env["PATH"].split(os.pathsep)[0]
    assert first_entry == str(venv / "bin")
    assert env["VIRTUAL_ENV"] == str(venv)


def test_venv_env_drops_pythonhome(tmp_path: Path) -> None:
    """A stale PYTHONHOME would point the venv interpreter elsewhere."""
    toolchain = _Recorder(tmp_path / "venv", "pip install .")

    original = os.environ.get("PYTHONHOME")
    os.environ["PYTHONHOME"] = "/somewhere/else"
    try:
        assert "PYTHONHOME" not in toolchain._venv_env()
    finally:
        if original is None:
            os.environ.pop("PYTHONHOME", None)
        else:
            os.environ["PYTHONHOME"] = original


def test_no_declared_build_leaves_the_toolchain_in_charge(tmp_path: Path) -> None:
    """With no `[build].build`, nothing is run and the caller installs normally."""
    toolchain = _Recorder(tmp_path / "venv", None)

    assert toolchain._run_declared_build(env=toolchain._venv_env()) is False
    assert toolchain.calls == []
