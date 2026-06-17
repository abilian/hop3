# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for CatalogService: index-driven load, availability, reload (ADR 049)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hop3.server.catalog import service as service_module
from hop3.server.catalog.service import CatalogService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_singleton():
    CatalogService.reset()
    yield
    CatalogService.reset()


def _app(catalog_dir: Path, app_id: str) -> None:
    d = catalog_dir / app_id
    d.mkdir(parents=True)
    (d / "hop3.toml").write_text(f'[metadata]\nid = "{app_id}"\ntitle = "{app_id}"\n')


def _index(catalog_dir: Path, app_ids: list[str]) -> None:
    index = {
        "format": 1,
        "serial": 1,
        "apps": [
            {"id": a, "files": [{"path": f"{a}/hop3.toml", "sha256": "0" * 64}]}
            for a in app_ids
        ],
    }
    (catalog_dir / "index.json").write_text(json.dumps(index))


def test_load_from_index_only_loads_indexed_apps(tmp_path):
    # F1: a directory on disk but absent from the signed index must NOT be loaded.
    cat = tmp_path / "catalog"
    _app(cat, "wanted")
    _app(cat, "ghost")  # present on disk, not in the index
    _index(cat, ["wanted"])

    svc = CatalogService.get_instance()
    svc.load(cat)

    assert {a.id for a in svc.list_apps()} == {"wanted"}
    assert svc.is_available()


def test_dev_fallback_scans_when_no_index(tmp_path):
    cat = tmp_path / "catalog"
    _app(cat, "a")
    _app(cat, "b")  # no index.json → dev/local scan loads both

    svc = CatalogService.get_instance()
    svc.load(cat)

    assert {a.id for a in svc.list_apps()} == {"a", "b"}


def test_unavailable_when_catalog_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        service_module, "_default_catalog_dir", lambda: tmp_path / "nope"
    )
    svc = CatalogService.get_instance()

    assert svc.is_available() is False
    assert svc.list_apps() == []
    assert svc.get_featured_apps() == []


def test_reload_reflects_updated_catalog(tmp_path, monkeypatch):
    cat = tmp_path / "catalog"
    _app(cat, "a")
    _index(cat, ["a"])
    monkeypatch.setattr(service_module, "_default_catalog_dir", lambda: cat)

    svc = CatalogService.get_instance()
    assert {a.id for a in svc.list_apps()} == {"a"}

    _app(cat, "b")
    _index(cat, ["a", "b"])
    svc.reload()

    assert {a.id for a in svc.list_apps()} == {"a", "b"}
