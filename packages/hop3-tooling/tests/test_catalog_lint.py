# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the catalog presentation gate."""

from __future__ import annotations

import pytest
from hop3_tooling.catalog_lint import lint_catalog

COMPLETE_RECIPE = """
[metadata]
id = "gitea"
title = "Gitea"
version = "1.22.0"
description = "Self-hosted Git service"
homepage = "https://gitea.io/"
license = "MIT"
author = "Gitea"

[build]
builder = "local"

[run]
start = "./gitea web"
"""

COMPLETE_OVERLAY = """
[catalog]
category = "Development"
tags = ["go", "git", "forge"]
memory = "512MB"
"""


def _app(
    apps_dir,
    name="gitea",
    *,
    recipe=COMPLETE_RECIPE,
    overlay=COMPLETE_OVERLAY,
    app_id=None,
):
    app_dir = apps_dir / name
    app_dir.mkdir(parents=True)
    # The id comes from [metadata], not the directory: an entry keeps its
    # identity wherever it sits.
    (app_dir / "hop3.toml").write_text(
        recipe.replace('id = "gitea"', f'id = "{app_id or name}"')
    )
    if overlay is not None:
        (app_dir / "catalog.toml").write_text(overlay)
    (app_dir / "icon.webp").write_bytes(b"RIFF____WEBPVP8 ")
    shots = app_dir / "screenshots"
    shots.mkdir()
    (shots / f"{name}-01-login.png").write_bytes(b"png")
    return app_dir


@pytest.fixture
def apps_dir(tmp_path):
    return tmp_path / "apps"


def test_a_complete_entry_passes(apps_dir):
    _app(apps_dir)

    assert lint_catalog(apps_dir) == []


def test_an_entry_that_does_not_describe_itself_fails(apps_dir):
    """
    The `Bookstack-Nix` case: no `[metadata]`, so the loader invents a title.

    Fifteen published entries were in this state — a synthesised title from the
    directory name, no version, no description — and every existing check
    passed them, because none asked whether an entry describes itself.
    """
    _app(apps_dir, recipe='[build]\nbuilder = "nix"\n')

    rules = {v.rule for v in lint_catalog(apps_dir)}

    assert "no description" in rules
    assert "no version" in rules


def test_other_is_not_a_category(apps_dir):
    """`Other` is what the tag mapping returns when it recognises nothing."""
    _app(
        apps_dir,
        overlay='[catalog]\ncategory = "Other"\ntags = ["x"]\nmemory = "1GB"\n',
    )

    violations = lint_catalog(apps_dir)

    assert [v.rule for v in violations] == ["uncategorized"]
    assert "pick one of" in violations[0].detail


@pytest.mark.parametrize(
    ("overlay", "expected"),
    [
        ('[catalog]\ntags = ["x"]\nmemory = "1GB"\n', "no category"),
        ('[catalog]\ncategory = "Development"\nmemory = "1GB"\n', "no tags"),
        ('[catalog]\ncategory = "Development"\ntags = ["x"]\n', "no memory estimate"),
    ],
)
def test_each_missing_overlay_field_is_named(apps_dir, overlay, expected):
    _app(apps_dir, overlay=overlay)

    assert [v.rule for v in lint_catalog(apps_dir)] == [expected]


def test_a_missing_icon_is_caught(apps_dir):
    app_dir = _app(apps_dir)
    (app_dir / "icon.webp").unlink()

    assert [v.rule for v in lint_catalog(apps_dir)] == ["no icon"]


def test_a_missing_screenshot_is_caught(apps_dir):
    app_dir = _app(apps_dir)
    (app_dir / "screenshots" / "gitea-01-login.png").unlink()

    assert [v.rule for v in lint_catalog(apps_dir)] == ["no screenshots"]


def test_every_violation_is_reported_not_just_the_first(apps_dir):
    """
    A gate that stops at the first problem takes N runs to fix N problems.
    """
    app_dir = _app(apps_dir, overlay=None)
    (app_dir / "icon.webp").unlink()

    rules = {v.rule for v in lint_catalog(apps_dir)}

    assert {"no category", "no tags", "no memory estimate", "no icon"} <= rules


def test_violations_name_the_app(apps_dir):
    """With 55 entries, a violation that does not say which app is useless."""
    _app(apps_dir, "gitea")
    _app(
        apps_dir,
        "forgejo",
        overlay='[catalog]\ncategory = "Development"\ntags = ["x"]\n',
    )

    violations = lint_catalog(apps_dir)

    assert [v.app_id for v in violations] == ["forgejo"]
    assert str(violations[0]).startswith("forgejo: no memory estimate")


def test_two_entries_with_one_id_are_caught(apps_dir):
    """
    The service keys apps by id, so the second silently replaces the first.

    Nothing else notices: both directories validate, both are published, and
    one application is simply absent from the catalog a server loads.
    """
    _app(apps_dir, "gitea")
    _app(apps_dir, "gitea-copy", app_id="gitea")  # a second dir claiming one id

    violations = lint_catalog(apps_dir)

    assert [v.rule for v in violations] == ["duplicate id"]
    assert "gitea-copy" in violations[0].detail


def test_an_empty_catalog_is_an_error(apps_dir):
    """Zero entries must not read as zero violations."""
    apps_dir.mkdir()

    with pytest.raises(ValueError, match="no catalog apps"):
        lint_catalog(apps_dir)


def test_a_catalog_with_nothing_publishable_is_a_different_error(apps_dir):
    """
    Recipes present but none offered — a real state, and still a failure.

    Distinct from the empty tree above: that one means a wrong path, this one
    means the catalog would be signed with nothing in it, unpublishing every app
    on every node. The message has to say which, or the fix is a guess.
    """
    apps_dir.mkdir()
    _app(apps_dir / "alpha", name="grafana")

    with pytest.raises(ValueError, match="all 1 recipe") as exc_info:
        lint_catalog(apps_dir)

    assert "alpha" in str(exc_info.value)


def test_unpublished_entries_are_not_held_to_the_presentation_bar(apps_dir):
    """
    An `alpha` recipe has no icon and no screenshot because nobody is offered it.

    Linting it would leave deletion as the only way to go green, discarding the
    record of why the app is hard — which is what keeping it is for.
    """
    apps_dir.mkdir()
    _app(apps_dir / "golden", name="gitea")
    bare = apps_dir / "alpha" / "grafana"
    bare.mkdir(parents=True)
    (bare / "hop3.toml").write_text(COMPLETE_RECIPE.replace('"gitea"', '"grafana"'))

    assert lint_catalog(apps_dir) == []
