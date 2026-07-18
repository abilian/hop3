# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the catalog drift + promote logic (ADR 057)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from hop3_tooling.catalog import compare_app, promote_app, recipe_files


def _make_app(base: Path, *, toml: str = "id = 'app'\n", setup: str = "echo hi\n") -> Path:
    (base / "scripts").mkdir(parents=True)
    (base / "hop3.toml").write_text(toml)
    (base / "scripts" / "setup.sh").write_text(setup)
    return base


def test_recipe_files_excludes_overlay(tmp_path):
    app = _make_app(tmp_path / "app")
    (app / "catalog.toml").write_text("[catalog]\n")
    (app / "readme.md").write_text("# app\n")
    files = recipe_files(app)
    assert set(files) == {"hop3.toml", "scripts/setup.sh"}


def test_compare_identical_is_in_sync(tmp_path):
    src = _make_app(tmp_path / "src")
    cat = _make_app(tmp_path / "cat")
    assert compare_app(cat, src) == []


def test_compare_ignores_overlay(tmp_path):
    src = _make_app(tmp_path / "src")
    cat = _make_app(tmp_path / "cat")
    (cat / "catalog.toml").write_text("[catalog]\n")
    (cat / "readme.md").write_text("# app\n")
    assert compare_app(cat, src) == []


def test_compare_detects_recipe_diff(tmp_path):
    src = _make_app(tmp_path / "src")
    cat = _make_app(tmp_path / "cat", toml="id = 'app'\n# hand edit\n")
    assert any("differs" in i for i in compare_app(cat, src))


def test_compare_detects_extra_catalog_script(tmp_path):
    src = _make_app(tmp_path / "src")
    cat = _make_app(tmp_path / "cat")
    (cat / "scripts" / "extra.sh").write_text("echo x\n")
    assert any("catalog-only" in i for i in compare_app(cat, src))


def test_compare_missing_source_reported(tmp_path):
    cat = _make_app(tmp_path / "cat")
    assert compare_app(cat, tmp_path / "nope")


def test_promote_makes_recipe_identical_and_keeps_overlay(tmp_path):
    src_root = tmp_path / "src"
    cat_root = tmp_path / "cat"
    _make_app(src_root / "app", toml="id = 'app'\nversion = '2'\n")
    cat_app = _make_app(cat_root / "app", toml="id = 'app'\nversion = '1'\n")
    # catalog-authored overlay + a stale script that promotion must remove
    (cat_app / "catalog.toml").write_text("[catalog]\n")
    (cat_app / "scripts" / "stale.sh").write_text("echo stale\n")

    promote_app("app", src_root, cat_root)

    assert compare_app(cat_app, src_root / "app") == []  # recipe now identical
    assert (cat_app / "catalog.toml").exists()  # overlay preserved
    assert not (cat_app / "scripts" / "stale.sh").exists()  # stale script gone
