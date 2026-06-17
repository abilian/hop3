# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The web-side cached catalog: per-mode counts + human titles for the UI.

These back the dropdown "(N)" counts and the "Demo 1: uWSGI Deployment" titles
shown in run views (instead of the path leaf "demo01"). They scan the repo's
apps/ tree, so they're real-catalog assertions, not stubs.
"""

from __future__ import annotations

from hop3_testlab.catalog import (
    mode_counts,
    tests_grouped as grouped_tests,  # avoid test* collection
    title_map,
    valid_test_names,
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


def test_tests_grouped_has_display_fields():
    rows = {r["name"]: r for r in grouped_tests()}
    demo = rows["demos/demo01"]
    assert demo["title"] == "Demo 1: uWSGI Deployment"
    assert demo["type"] == "demo"
    flask = rows["apps/test-apps-procfile/010-flask-pip-wsgi"]
    assert flask["language"] == "python"
    assert flask["variant"] == "procfile"


def test_valid_test_names_includes_seed():
    names = valid_test_names()
    assert "demos/demo01" in names
    assert "apps/test-apps-procfile/000-static" in names
