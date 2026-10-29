# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The uv a server builds `uv.lock` apps with is pinned, installed in every mode,
and reconciled on every install.

It was installed only for `--from git`, unpinned, into the server venv (off
every PATH), so the Python toolchain fell back to fetching uv at build time.
"""

from __future__ import annotations

import subprocess

import pytest
from hop3_installer.common import InstallStepError
from hop3_installer.server_installer import deps_common
from hop3_installer.server_installer.deps_common import UV_VERSION, install_uv


class FakeHost:
    """Records commands; `pip install` creates the uv binary in the venv."""

    def __init__(self, venv, hop3_uv_version: str = UV_VERSION) -> None:
        self.venv = venv
        self.hop3_uv_version = hop3_uv_version
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **_kw) -> subprocess.CompletedProcess:
        cmd = list(cmd)
        self.calls.append(cmd)
        if cmd[1:3] == ["-m", "venv"]:
            (self.venv / "bin").mkdir(parents=True)
            (self.venv / "bin" / "python").touch()
        if cmd[1:2] == ["install"]:
            (self.venv / "bin" / "uv").touch()
        if cmd == ["uv", "--version"]:
            return subprocess.CompletedProcess(
                cmd, 0, f"uv {self.hop3_uv_version} (abc 2026-10-20)\n", ""
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")


def _install(tmp_path, host: FakeHost) -> None:
    install_uv(run=host, as_hop3=host, venv=host.venv, link=tmp_path / "uv")


def test_the_pin_is_an_exact_version():
    assert UV_VERSION.count(".") == 2


def test_uv_is_installed_at_the_pin_and_linked(tmp_path):
    host = FakeHost(tmp_path / "venv")
    _install(tmp_path, host)
    assert [
        str(host.venv / "bin" / "pip"),
        "install",
        f"uv=={UV_VERSION}",
    ] in host.calls
    assert (tmp_path / "uv").resolve() == (host.venv / "bin" / "uv").resolve()


def test_an_existing_install_is_reconciled_not_skipped(tmp_path):
    host = FakeHost(tmp_path / "venv")
    _install(tmp_path, host)
    host.calls.clear()
    _install(tmp_path, host)
    assert [
        str(host.venv / "bin" / "pip"),
        "install",
        f"uv=={UV_VERSION}",
    ] in host.calls
    assert ["uv", "--version"] in host.calls


def test_another_uv_ahead_on_the_hop3_path_fails_the_install(tmp_path):
    host = FakeHost(tmp_path / "venv", hop3_uv_version="0.4.0")
    with pytest.raises(InstallStepError, match=r"0\.4\.0"):
        _install(tmp_path, host)


def test_the_installed_location_is_one_the_python_toolchain_searches():
    # hop3-server's PythonToolchain._uv_candidates includes /usr/local/bin/uv.
    assert str(deps_common.UV_BIN) == "/usr/local/bin/uv"
