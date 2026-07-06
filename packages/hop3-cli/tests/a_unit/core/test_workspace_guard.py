# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the uv-workspace-member deploy guard (core.workspace_guard)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_cli.core.workspace_guard import check_workspace_dependency

if TYPE_CHECKING:
    from pathlib import Path


def _make_workspace(root: Path, app_a_deps: list[str]) -> Path:
    """A 2-member workspace: app-a (deps = app_a_deps) + sibling app-b."""
    (root / "pyproject.toml").write_text(
        "[tool.uv.workspace]\nmembers = ['packages/*']\n"
    )
    a = root / "packages" / "app-a"
    b = root / "packages" / "app-b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    deps = ", ".join(f'"{d}"' for d in app_a_deps)
    (a / "pyproject.toml").write_text(
        f'[project]\nname = "app-a"\ndependencies = [{deps}]\n'
    )
    (b / "pyproject.toml").write_text('[project]\nname = "app-b"\n')
    return a


def test_fires_on_unpinned_sibling(tmp_path):
    """Deploying app-a alone, which depends on sibling app-b unpinned, fires."""
    app_a = _make_workspace(tmp_path, ["app-b"])

    issue = check_workspace_dependency(app_a, home=tmp_path)

    assert issue.is_problem
    assert issue.siblings == ("app-b",)
    assert issue.workspace_root == tmp_path.resolve()
    assert "app-b" in issue.message
    assert "PyPI" in issue.message


def test_normalizes_names(tmp_path):
    """Underscore/dot variants still match the sibling (PEP 503)."""
    app_a = _make_workspace(tmp_path, ["App_B"])
    assert check_workspace_dependency(app_a, home=tmp_path).is_problem


def test_exact_pin_is_allowed(tmp_path):
    """An explicit ``==`` pin opts into the PyPI release on purpose."""
    app_a = _make_workspace(tmp_path, ["app-b==1.2.3"])
    assert not check_workspace_dependency(app_a, home=tmp_path).is_problem


def test_loose_constraint_still_fires(tmp_path):
    """A non-exact constraint (>=) still resolves to a PyPI release — fires."""
    app_a = _make_workspace(tmp_path, ["app-b>=1.0"])
    assert check_workspace_dependency(app_a, home=tmp_path).is_problem


def test_external_dependency_is_ignored(tmp_path):
    """A dep that isn't a workspace member is fine."""
    app_a = _make_workspace(tmp_path, ["requests>=2"])
    assert not check_workspace_dependency(app_a, home=tmp_path).is_problem


def test_deploying_workspace_root_is_fine(tmp_path):
    """Deploying the workspace root itself ships the siblings — no problem."""
    _make_workspace(tmp_path, ["app-b"])
    assert not check_workspace_dependency(tmp_path, home=tmp_path).is_problem


def test_non_workspace_dir_is_fine(tmp_path):
    """A standalone project (no enclosing workspace) is never flagged."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "solo"\ndependencies = ["requests"]\n'
    )
    assert not check_workspace_dependency(tmp_path, home=tmp_path).is_problem


def test_no_pyproject_is_fine(tmp_path):
    """A source dir without a pyproject (e.g. a Procfile app) is never flagged."""
    assert not check_workspace_dependency(tmp_path, home=tmp_path).is_problem
