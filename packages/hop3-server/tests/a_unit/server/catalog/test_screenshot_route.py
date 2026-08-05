# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The screenshot route is public and takes a filename from the URL.

It must select from the names the app actually ships rather than join the URL
onto a path, so a crafted filename cannot reach outside the app's own verified
directory (the same rule the icon route follows — ADR 049 F6).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from litestar.response import File, Redirect

from hop3.server.catalog import CatalogService
from hop3.server.controllers.catalog import CatalogController

RECIPE = '[metadata]\nid = "gitea"\ntitle = "Gitea"\n'


@pytest.fixture
def catalog(tmp_path):
    app_dir = tmp_path / "gitea"
    (app_dir / "screenshots").mkdir(parents=True)
    (app_dir / "hop3.toml").write_text(RECIPE)
    (app_dir / "screenshots" / "gitea-01-login.png").write_bytes(b"png")
    (tmp_path / "secret.png").write_bytes(b"not ours")

    CatalogService.reset()
    CatalogService.get_instance().load(tmp_path)
    yield tmp_path
    CatalogService.reset()


def _serve(app_id: str, filename: str):
    # `.fn` is the handler under Litestar's route-handler wrapper; the handler
    # reads no instance state, so an unbound call is the whole behaviour.
    return CatalogController.catalog_screenshot.fn(None, app_id, filename)


def test_a_shipped_screenshot_is_served(catalog):
    response = _serve("gitea", "gitea-01-login.png")

    assert isinstance(response, File)
    assert Path(response.file_path).name == "gitea-01-login.png"
    assert response.media_type == "image/png"
    # A mislabeled file must not be reinterpreted as active content.
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize(
    "filename",
    [
        "../secret.png",
        "../../secret.png",
        "screenshots/../../secret.png",
        "/etc/passwd",
        "nope.png",
    ],
)
def test_a_filename_the_app_does_not_ship_is_refused(catalog, filename):
    assert isinstance(_serve("gitea", filename), Redirect)


def test_an_unknown_app_is_refused(catalog):
    assert isinstance(_serve("nonexistent", "gitea-01-login.png"), Redirect)
