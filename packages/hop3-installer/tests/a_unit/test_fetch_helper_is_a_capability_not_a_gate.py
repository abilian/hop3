# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A server that predates hop3-fetch must still install.

`publish_fetch_helper` originally raised when the venv had no `hop3-fetch`, on
the reasoning that a missing helper is better caught at install time than as
"command not found" inside a recipe. That reasoning ignored what this installer
is for: it installs *whatever version it is asked for* — from git, from a
`--version` pin, from PyPI — and every version older than the helper has none to
publish. The from-git e2e test failed exactly there, aborting a perfectly good
install.

So a server without the helper is a capability the installer reports and moves
past. A helper that exists but cannot be linked is still an error, because then
every recipe needing it fails with nothing pointing back here.
"""

from __future__ import annotations

import pytest
from hop3_installer.server_installer import python as installer_python


def test_a_server_without_the_helper_installs_anyway(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(installer_python, "VENV_DIR", tmp_path)

    installer_python.publish_fetch_helper()  # must not raise

    assert "ships no hop3-fetch" in capsys.readouterr().out


def test_a_helper_that_cannot_be_published_is_an_error(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "hop3-fetch").write_text("#!/bin/sh\n")
    monkeypatch.setattr(installer_python, "VENV_DIR", tmp_path)
    monkeypatch.setattr(installer_python, "create_symlink", lambda *_: False)

    with pytest.raises(OSError, match="could not be linked"):
        installer_python.publish_fetch_helper()


def test_a_present_helper_is_published(monkeypatch, tmp_path, capsys):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "hop3-fetch").write_text("#!/bin/sh\n")
    linked = []
    monkeypatch.setattr(installer_python, "VENV_DIR", tmp_path)
    monkeypatch.setattr(
        installer_python,
        "create_symlink",
        lambda src, dst: (linked.append((src, dst)), True)[1],
    )

    installer_python.publish_fetch_helper()

    assert linked == [(bin_dir / "hop3-fetch", installer_python.FETCH_HELPER_LINK)]
    assert "published" in capsys.readouterr().out
