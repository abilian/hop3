# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The web-side cached catalog: per-mode counts + human titles for the UI.

These back the dropdown "(N)" counts and the "Demo 1: uWSGI Deployment" titles
shown in run views (instead of the path leaf "demo01"). They scan the repo's
apps/ tree, so they're real-catalog assertions, not stubs.
"""

from __future__ import annotations

import pytest
from hop3_testing.catalog import scanner
from hop3_testing.targets.helpers import find_project_root
from hop3_testlab.catalog import (
    get_catalog,
    resolve_selector,
    title_map,
)


@pytest.fixture
def fresh_catalog():
    """`get_catalog` caches per process: scan again, and leave no scan behind."""
    get_catalog.cache_clear()
    yield
    get_catalog.cache_clear()


def test_title_map_uses_human_titles(fresh_catalog):
    titles = title_map()
    assert titles["demos/demo01"] == "Demo 1: uWSGI Deployment"
    # Tutorials use their markdown H1.
    assert "Flask" in titles["docs/tutorials/python/flask.md"]


def test_title_map_keys_catalog_apps_by_id(fresh_catalog, catalog_apps, monkeypatch):
    # Catalog apps are keyed by bare id, not by path — and the key is a *published*
    # app: this asserted on `apps/real-apps-native/etherpad`, a tree that moved to
    # the catalog, where etherpad sits at `alpha` and outside the default scan set.
    monkeypatch.setattr(scanner, "default_catalog_apps", lambda root: catalog_apps)
    assert title_map()["bookstack"] == "BookStack"


def test_resolve_selector_matches_app_dirs():
    # A glob resolves server-side against the catalog (real app dirs only).
    names = resolve_selector(find_project_root(), "apps/test-apps-procfile/*")
    assert "apps/test-apps-procfile/000-static" in names
    assert all(n.startswith("apps/test-apps-procfile/") for n in names)
    # Literal, not shell-expanded: a non-matching pattern selects nothing.
    assert resolve_selector(find_project_root(), "no-such-dir/*") == []
