# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The web-side cached catalog: per-mode counts + human titles for the UI.

These back the dropdown "(N)" counts and the "Demo 1: uWSGI Deployment" titles
shown in run views (instead of the path leaf "demo01"). They scan the repo's
apps/ tree, so they're real-catalog assertions, not stubs.
"""

from __future__ import annotations

from hop3_testing.targets.helpers import find_project_root

from hop3_testlab.catalog import (
    mode_counts,
    resolve_selector,
    title_map,
)


def test_mode_counts_cover_the_ladder():
    counts = mode_counts()
    # The seven built-in profiles all get a count, ordered smallest → largest.
    for name in (
        "smoke",
        "ci",
        "curated",
        "tag-coverage",
        "combo-coverage",
        "nightly",
        "full",
    ):
        assert counts.get(name, 0) > 0
    assert counts["smoke"] <= counts["ci"] <= counts["full"]


def test_title_map_uses_human_titles():
    titles = title_map()
    assert titles["demos/demo01"] == "Demo 1: uWSGI Deployment"
    assert titles["apps/real-apps-native/etherpad"] == "Etherpad"
    # Tutorials use their markdown H1.
    assert "Flask" in titles["docs/tutorials/python/flask.md"]


def test_resolve_selector_matches_app_dirs():
    # A glob resolves server-side against the catalog (real app dirs only).
    names = resolve_selector(find_project_root(), "apps/test-apps-procfile/*")
    assert "apps/test-apps-procfile/000-static" in names
    assert all(n.startswith("apps/test-apps-procfile/") for n in names)
    # Literal, not shell-expanded: a non-matching pattern selects nothing.
    assert resolve_selector(find_project_root(), "no-such-dir/*") == []
