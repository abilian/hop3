# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The site builder renders a catalog checkout to static HTML."""

from __future__ import annotations

import json
import re

import pytest
from hop3_marketplace.builder import build

from hop3.commands._base import Command
from hop3.lib.registry import lookup
from hop3.lib.scanner import scan_package

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


def test_the_install_command_is_a_real_command(catalog, tmp_path):
    """
    The site tells people what to type; it must be something that runs.

    The page shipped `hop3 apps:install <id>` — a colon-style verb from a CLI
    generation ago, which no version of Hop3 has ever accepted. Nothing caught
    it because a template string is not executed by anything. So rather than
    correct the literal and move on, this reads the command back out of the
    rendered page and checks it against the server's own command registry: if
    the CLI renames or drops it, the site fails to build.
    """
    out = tmp_path / "site"
    build(catalog, out)
    page = (out / "apps" / "gitea" / "index.html").read_text()

    match = re.search(r'id="install-cmd"[^>]*>([^<]+)<', page)
    assert match, "the detail page no longer shows an install command"

    tokens = match.group(1).split()
    assert tokens[0] == "hop3"
    # Everything between `hop3` and the app id is the command name.
    verb = tuple(t for t in tokens[1:-1] if not t.startswith("-"))
    assert tokens[-1] == "gitea"

    scan_package("hop3.commands")
    registered = {command.name for command in lookup(Command)}
    assert verb in registered, (
        f"the site advertises `hop3 {' '.join(verb)}`, which is not a command"
    )


def test_screenshots_are_discovered_copied_and_shown(catalog, tmp_path):
    """
    An app that ships captures gets them on its page without declaring them.

    Every entry in the real catalog said `screenshots = []` while shipping two
    PNGs, because the field was a list in 55 files mirroring 55 directories.
    The files are the source of truth; the field is an override.
    """
    shots = catalog / "gitea" / "screenshots"
    shots.mkdir()
    (shots / "gitea-02-signed-in.png").write_bytes(b"\x89PNG\r\n\x1a\n second")
    (shots / "gitea-01-login.png").write_bytes(b"\x89PNG\r\n\x1a\n first")

    out = tmp_path / "site"
    build(catalog, out)

    copied = out / "assets" / "screenshots" / "gitea"
    assert (copied / "gitea-01-login.png").is_file()
    assert (copied / "gitea-02-signed-in.png").is_file()

    page = (out / "apps" / "gitea" / "index.html").read_text()
    assert "Screenshots" in page
    # Filename order, so the sign-in page comes before the page behind it.
    first = page.index("gitea-01-login.png")
    second = page.index("gitea-02-signed-in.png")
    assert first < second


def test_an_app_without_screenshots_shows_no_gallery(catalog, tmp_path):
    """The section is absent, not an empty heading over nothing."""
    out = tmp_path / "site"
    build(catalog, out)

    page = (out / "apps" / "gitea" / "index.html").read_text()

    assert "Screenshots" not in page
