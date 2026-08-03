# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The loader reads the catalog.toml overlay on top of the deployable recipe.

Identity comes from hop3.toml [metadata] (incl. `homepage`); presentation
(category/tags/featured/memory/license_note/screenshots) comes from catalog.toml
when present, with graceful fallbacks otherwise (ADR 049 / catalog repo CLAUDE.md).
"""

from __future__ import annotations

import pytest

from hop3.server.catalog.loader import load_app
from hop3.server.catalog.policy import CatalogSpecError
from hop3.server.catalog.taxonomy import build_categories

RECIPE = (
    "[metadata]\n"
    'id = "gitea"\n'
    'title = "Gitea"\n'
    'description = "Self-hosted Git service"\n'
    'homepage = "https://gitea.io/"\n'
    'license = "MIT"\n'
    'categories = ["git"]\n'
    "[build]\n"
    'builder = "local"\n'
    "[run]\n"
    'start = "./gitea web"\n'
)


def _write(app_dir, hop3, catalog=None):
    app_dir.mkdir(parents=True)
    (app_dir / "hop3.toml").write_text(hop3)
    if catalog is not None:
        (app_dir / "catalog.toml").write_text(catalog)


def test_overlay_supplies_presentation_fields(tmp_path):
    app_dir = tmp_path / "gitea"
    _write(
        app_dir,
        RECIPE,
        "[catalog]\n"
        'category = "Development"\n'
        'tags = ["go", "git", "forge"]\n'
        "featured = true\n"
        'memory = "512MB"\n'
        'license_note = "source-available"\n'
        'screenshots = ["screenshots/a.png"]\n',
    )
    app = load_app(app_dir)

    assert app.website == "https://gitea.io/"  # homepage -> website
    assert app.tags == ["go", "git", "forge"]  # overlay tags win
    assert app.category == "Development"  # explicit
    assert app.featured is True
    assert app.memory == "512MB"
    assert app.resource_tier == "medium"
    assert app.license_note == "source-available"
    assert app.screenshots == ["screenshots/a.png"]

    build_categories([app])
    assert app.category == "Development"  # explicit category respected, not re-derived


def test_no_overlay_falls_back_to_metadata(tmp_path):
    app_dir = tmp_path / "gitea"
    _write(app_dir, RECIPE)  # no catalog.toml
    app = load_app(app_dir)

    assert app.website == "https://gitea.io/"
    assert app.tags == ["git"]  # [metadata].categories -> tags
    assert app.featured is False
    assert app.license_note == ""

    build_categories([app])
    assert app.category == "Development"  # derived from the "git" tag


def test_malformed_overlay_is_refused_not_ignored(tmp_path):
    """
    A broken overlay must stop the app loading, not degrade it quietly.

    Logging and carrying on renders the app with whatever the recipe alone can
    supply — no category, no memory, no tags — which is indistinguishable from
    an app that simply has no overlay. That is how 55 identical cards in one
    category went unnoticed for weeks. The publish gate is where a malformed
    overlay gets caught; the reader's job is to refuse it.
    """
    app_dir = tmp_path / "gitea"
    _write(app_dir, RECIPE, "this is not = valid toml [[[")

    with pytest.raises(CatalogSpecError, match=r"malformed catalog\.toml"):
        load_app(app_dir)


def test_addons_are_read_as_services(tmp_path):
    """
    Services come from `[[addons]]`, the spelling recipes actually use.

    The loader only understood `[[provider]]`, which no catalog recipe carries,
    so every app in the catalog displayed as needing no services at all.
    """
    app_dir = tmp_path / "gitea"
    _write(app_dir, RECIPE + '[[addons]]\ntype = "postgres"\n')

    app = load_app(app_dir)

    assert app.providers == ["postgres"]


def test_declared_category_beats_the_tag_mapping(tmp_path):
    """
    A hand-filed app stays where it was filed.

    The tag mapping returns whichever category matches first, so an app tagged
    both "git" and "wiki" lands wherever dict order puts it. When someone has
    already stated the category, that is the answer.
    """
    app_dir = tmp_path / "gitea"
    _write(
        app_dir,
        RECIPE,
        '[catalog]\ncategory = "Collaboration"\ntags = ["git", "wiki", "forge"]\n',
    )

    app = load_app(app_dir)
    build_categories([app])

    assert app.category == "Collaboration"


def test_screenshots_are_discovered_from_the_app_directory(tmp_path):
    """No overlay entry needed: an app's own captures are what it shows."""
    app_dir = tmp_path / "gitea"
    _write(app_dir, RECIPE)
    shots = app_dir / "screenshots"
    shots.mkdir()
    (shots / "gitea-02-signed-in.png").write_bytes(b"png")
    (shots / "gitea-01-login.png").write_bytes(b"png")

    app = load_app(app_dir)

    assert app.screenshots == [
        "screenshots/gitea-01-login.png",
        "screenshots/gitea-02-signed-in.png",
    ]


def test_a_declared_screenshot_list_wins_over_discovery(tmp_path):
    """The overlay is the override: a subset, or a different order."""
    app_dir = tmp_path / "gitea"
    _write(
        app_dir,
        RECIPE,
        '[catalog]\nscreenshots = ["screenshots/gitea-02-signed-in.png"]\n',
    )
    shots = app_dir / "screenshots"
    shots.mkdir()
    (shots / "gitea-01-login.png").write_bytes(b"png")
    (shots / "gitea-02-signed-in.png").write_bytes(b"png")

    app = load_app(app_dir)

    assert app.screenshots == ["screenshots/gitea-02-signed-in.png"]


def test_screenshot_discovery_refuses_svg_and_escapes(tmp_path):
    """
    Same containment as the icon path: raster only, inside the app's own dir.

    A catalog is fetched from a remote source, so a crafted entry must not be
    able to point the render path at an SVG (an XSS vector when inlined) or at
    a file outside the app (ADR 049 F6).
    """
    app_dir = tmp_path / "gitea"
    _write(app_dir, RECIPE)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"png")
    shots = app_dir / "screenshots"
    shots.mkdir()
    (shots / "logo.svg").write_text("<svg onload='alert(1)'/>")
    (shots / "escape.png").symlink_to(outside)
    (shots / "real.png").write_bytes(b"png")

    app = load_app(app_dir)

    assert app.screenshots == ["screenshots/real.png"]
