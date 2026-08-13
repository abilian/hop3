# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for locating catalog recipes (ADR 057, ADR 059).

This file used to test the drift check and the promote step, which compared a
catalog recipe against a "tested source" in this repository and copied one over
the other. Both premises are gone — the catalog holds the recipes now — so what
is left to test is finding them, across a layout where the directory says how
mature a recipe is and the id says how it is built.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_tooling.catalog import app_dirs, app_ids, find_repo_root, recipe_for

if TYPE_CHECKING:
    from pathlib import Path


def _recipe(root: Path, status: str, app_id: str) -> Path:
    d = root / status / app_id
    d.mkdir(parents=True)
    (d / "hop3.toml").write_text(f'[metadata]\nid = "{app_id}"\n')
    return d


def test_app_dirs_finds_recipes_across_statuses(tmp_path):
    _recipe(tmp_path, "golden", "gitea")
    _recipe(tmp_path, "beta", "gitea-nix")
    _recipe(tmp_path, "alpha", "grafana")

    found = app_dirs(tmp_path)

    assert set(found) == {"gitea", "gitea-nix", "grafana"}
    assert found["gitea-nix"].parent.name == "beta"


def test_the_flat_layout_still_resolves(tmp_path):
    """An older checkout, from before recipes were filed by maturity."""
    d = tmp_path / "gitea"
    d.mkdir()
    (d / "hop3.toml").write_text('[metadata]\nid = "gitea"\n')

    assert app_ids(tmp_path) == ["gitea"]


def test_a_status_directory_is_not_itself_an_app(tmp_path):
    """The flat version of this returned `["beta", "golden"]` — two "apps"."""
    _recipe(tmp_path, "golden", "gitea")

    assert app_ids(tmp_path) == ["gitea"]


def test_recipe_for_maps_a_variant_to_its_id_suffix(tmp_path):
    """
    The packaging is in the id, not the path.

    Callers used to build ``apps/real-apps-<variant>/<app>``, which cannot work
    once the directory means maturity: the same recipe moves between `golden`,
    `beta` and `alpha` as it earns or loses a status.
    """
    _recipe(tmp_path, "golden", "bookstack")
    _recipe(tmp_path, "beta", "bookstack-nix")
    _recipe(tmp_path, "beta", "bookstack-nixgen")
    _recipe(tmp_path, "alpha", "bookstack-docker")

    assert recipe_for("bookstack", "native", tmp_path).parent.name == "golden"
    assert recipe_for("bookstack", "nix", tmp_path).name == "bookstack-nix"
    assert recipe_for("bookstack", "nix-gen", tmp_path).name == "bookstack-nixgen"
    assert recipe_for("bookstack", "nix-template", tmp_path).name == "bookstack-nixgen"
    assert recipe_for("bookstack", "docker", tmp_path).name == "bookstack-docker"


def test_recipe_for_returns_none_rather_than_guessing(tmp_path):
    _recipe(tmp_path, "golden", "bookstack")

    assert recipe_for("bookstack", "nix", tmp_path) is None
    assert recipe_for("nosuchapp", "native", tmp_path) is None
    assert recipe_for("bookstack", "not-a-variant", tmp_path) is None


def test_the_repo_root_marker_is_not_an_apps_directory(tmp_path):
    """
    Root detection must not depend on a tree that can move.

    The marker was ``apps/real-apps-native``. Once those recipes moved to the
    catalog, that would have silently sent every caller to the fallback path.
    """
    root = tmp_path / "hop3"
    (root / "packages" / "hop3-server").mkdir(parents=True)
    nested = root / "packages" / "hop3-tooling"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == root
