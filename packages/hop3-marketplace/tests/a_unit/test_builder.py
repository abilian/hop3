# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The site builder renders a catalog checkout to static HTML."""

from __future__ import annotations

import json

import pytest
from hop3_marketplace.builder import build

RECIPE = """
[metadata]
id = "gitea"
title = "Gitea"
description = "Self-hosted Git service"
homepage = "https://gitea.io/"
license = "MIT"
author = "Gitea"

[build]
builder = "local"

[[addons]]
type = "postgres"

[run]
start = "./gitea web"
"""

OVERLAY = """
[catalog]
category = "Development"
tags = ["go", "git", "forge"]
featured = true
memory = "512MB"
"""


@pytest.fixture
def catalog(tmp_path):
    apps = tmp_path / "apps"
    app_dir = apps / "gitea"
    app_dir.mkdir(parents=True)
    (app_dir / "hop3.toml").write_text(RECIPE)
    (app_dir / "catalog.toml").write_text(OVERLAY)
    (app_dir / "icon.webp").write_bytes(b"RIFF____WEBPVP8 ")
    return apps


def test_build_renders_the_expected_pages(catalog, tmp_path):
    out = tmp_path / "site"

    count = build(catalog, out)

    assert count == 1
    assert (out / "index.html").is_file()
    assert (out / "apps" / "index.html").is_file()
    assert (out / "apps" / "gitea" / "index.html").is_file()
    assert (out / "category" / "development" / "index.html").is_file()
    assert (out / "about" / "index.html").is_file()


def test_detail_page_shows_what_the_catalog_declares(catalog, tmp_path):
    """
    The point of the overlay: a page that states licence, services and memory.

    Every one of these was blank until the loader read catalog.toml, and the
    page rendered anyway — which is why this asserts content and not just that
    a file exists.
    """
    out = tmp_path / "site"
    build(catalog, out)

    page = (out / "apps" / "gitea" / "index.html").read_text()

    assert "Gitea" in page
    assert "MIT" in page  # licence
    assert "postgres" in page  # services, from [[addons]]
    assert "512MB" in page  # memory, from the overlay
    assert "https://gitea.io/" in page  # homepage, not the legacy `website` key


def test_icons_are_served_as_files_not_dashboard_routes(catalog, tmp_path):
    """A static site has no icon route; the file has to be copied out."""
    out = tmp_path / "site"
    build(catalog, out)

    assert (out / "assets" / "icons" / "gitea.webp").is_file()
    assert "/assets/icons/gitea.webp" in (out / "index.html").read_text()
    assert "/dashboard/catalog/icons/" not in (out / "index.html").read_text()


def test_search_index_covers_every_app(catalog, tmp_path):
    out = tmp_path / "site"
    build(catalog, out)

    index = json.loads((out / "search-index.json").read_text())

    assert [entry["id"] for entry in index] == ["gitea"]
    assert index[0]["url"] == "/apps/gitea/"


def test_an_empty_catalog_is_an_error_not_an_empty_site(tmp_path):
    """
    Publishing a site with no apps would look like a successful build.

    The failure this guards against is a wrong --catalog path: the loader
    returns [], every page renders empty, and `make publish` ships it.
    """
    with pytest.raises(SystemExit, match="No catalog apps"):
        build(tmp_path / "nonexistent", tmp_path / "site")


def test_rendering_does_not_delete_the_signed_catalog(catalog, tmp_path):
    """
    `public/catalog/` belongs to `make stage`, not to the renderer.

    Rendering replaces the output directory, so without this a `make site`
    between two releases would remove the signed tarball from the web root and
    the next deploy would publish its absence — every deployed hop3-server
    losing its catalog source, with nothing reporting an error.
    """
    out = tmp_path / "site"
    signed = out / "catalog"
    signed.mkdir(parents=True)
    (signed / "catalog.tar.gz").write_bytes(b"signed bytes")
    (signed / "catalog.tar.gz.minisig").write_text("signature")

    build(catalog, out)

    assert (signed / "catalog.tar.gz").read_bytes() == b"signed bytes"
    assert (signed / "catalog.tar.gz.minisig").read_text() == "signature"
