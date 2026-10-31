# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
hop3-rootd is installed by root, into a venv root owns, from a source only root
can change.

It ran as root from hop3's venv, which hop3 (and so every app) can write: what
an app put there ran as root at the next restart. ``check_root_controlled`` is
the guard on what root installs from and runs. The tests run as an ordinary
user, so they accept that user's uid as "root" and nothing else.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from hop3_installer.common import InstallStepError
from hop3_installer.server_installer import python as mod
from hop3_installer.server_installer.config import ServerInstallerConfig

if TYPE_CHECKING:
    from pathlib import Path

#: Root, and the uid running the tests in its place.
ME = frozenset({0, os.getuid()})


def _tree(base: Path) -> Path:
    src = base / "hop3-rootd"
    (src / "src" / "hop3_rootd").mkdir(parents=True)
    (src / "pyproject.toml").write_text('[project]\nname = "hop3-rootd"\n')
    (src / "src" / "hop3_rootd" / "__init__.py").write_text("")
    for path in (src, *src.rglob("*")):
        path.chmod(0o755 if path.is_dir() else 0o644)
    return src


def test_a_tree_only_its_owner_can_write_is_accepted(tmp_path):
    mod.check_root_controlled(_tree(tmp_path), owners=ME)


def test_a_group_writable_file_is_refused(tmp_path):
    src = _tree(tmp_path)
    module = src / "src" / "hop3_rootd" / "__init__.py"
    module.chmod(0o664)
    with pytest.raises(InstallStepError, match=r"__init__\.py"):
        mod.check_root_controlled(src, owners=ME)


def test_a_tree_another_user_owns_is_refused(tmp_path):
    with pytest.raises(InstallStepError, match="owned by uid"):
        mod.check_root_controlled(_tree(tmp_path), owners=frozenset({0}))


def test_a_writable_directory_above_it_is_refused(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    src = _tree(shared)
    shared.chmod(0o777)
    with pytest.raises(InstallStepError, match="directory above it"):
        mod.check_root_controlled(src, owners=ME)


def test_a_sticky_directory_above_it_is_like_tmp(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    src = _tree(shared)
    shared.chmod(0o1777)
    mod.check_root_controlled(src, owners=ME)


def test_a_refused_local_source_installs_nothing(tmp_path, monkeypatch):
    """The check comes first: no venv, no pip, before the source is trusted."""
    (tmp_path / "hop3-server").mkdir()
    src = _tree(tmp_path)
    src.joinpath("pyproject.toml").chmod(0o666)
    ran: list[object] = []
    monkeypatch.setattr(mod, "run_cmd", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(mod, "run_as_hop3", lambda *a, **k: ran.append(a))
    config = ServerInstallerConfig(local_path=str(tmp_path / "hop3-server"))

    with pytest.raises(InstallStepError, match=r"pyproject\.toml"):
        mod.install_rootd_package(config)
    assert ran == []


def test_rootd_is_installed_by_root_into_its_own_venv(tmp_path, monkeypatch):
    venv = tmp_path / "opt" / "hop3-rootd"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("")
    monkeypatch.setattr(mod, "ROOTD_VENV_DIR", venv)
    check = mod.check_root_controlled
    monkeypatch.setattr(
        mod, "check_root_controlled", lambda path: check(path, owners=ME)
    )
    as_root: list[list[str]] = []
    as_hop3: list[list[str]] = []
    monkeypatch.setattr(mod, "run_cmd", lambda argv, **_k: as_root.append(argv))
    monkeypatch.setattr(mod, "run_as_hop3", lambda argv, **_k: as_hop3.append(argv))

    mod.install_rootd_package(ServerInstallerConfig(version="0.8.1"))

    pip = str(venv / "bin" / "pip")
    # pip first: Ubuntu 24.04's knows no --uploaded-prior-to (2026-10-30 e2e).
    assert as_root[0] == [pip, "install", "--upgrade", "pip"]
    assert [c[:2] for c in as_root[1:]] == [[pip, "install"], [pip, "install"]]
    assert as_root[-1][-1] == "hop3-rootd==0.8.1"
    # The copy older installers put in hop3's venv stays: the unit still runs
    # it until setup_rootd rewrites it (test_rootd.py).
    assert as_hop3 == []
    assert (venv / "pip.conf").read_text() == mod.PIP_COOLDOWN_CONF


def _link_out(tmp_path: Path, *, mode: int, directory: bool = False) -> Path:
    """A tree whose module is a root-owned symlink to a path outside it."""
    src = _tree(tmp_path / "upload")
    outside = tmp_path / "elsewhere"
    if directory:
        outside.mkdir()
    else:
        outside.write_text("import os\n")
    outside.chmod(mode)
    module = src / "src" / "hop3_rootd" / "__init__.py"
    module.unlink()
    module.symlink_to(outside)
    return src


def test_a_symlink_to_a_file_others_can_write_is_refused(tmp_path):
    """pip follows the link: the target is what root installs."""
    src = _link_out(tmp_path, mode=0o666)
    with pytest.raises(InstallStepError, match=r"__init__\.py -> .*elsewhere"):
        mod.check_root_controlled(src, owners=ME)


def test_a_symlink_to_a_directory_outside_the_tree_is_refused(tmp_path):
    src = _link_out(tmp_path, mode=0o755, directory=True)
    with pytest.raises(InstallStepError, match="not a file inside the tree"):
        mod.check_root_controlled(src, owners=ME)


def test_a_symlink_to_a_root_controlled_file_is_accepted(tmp_path):
    """A venv's ``bin/python3`` leads to the system interpreter."""
    mod.check_root_controlled(_link_out(tmp_path, mode=0o644), owners=ME)


def test_a_symlink_inside_the_tree_is_checked_there(tmp_path):
    src = _tree(tmp_path)
    (src / "src" / "link").symlink_to("hop3_rootd")
    mod.check_root_controlled(src, owners=ME)
