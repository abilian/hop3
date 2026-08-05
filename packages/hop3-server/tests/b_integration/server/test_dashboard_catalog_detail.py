# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
What the catalog detail page shows, rendered through the real app.

The page returned 200 while displaying none of this: the templates read
``initials_bg_color``, ``long_description`` and ``min_memory``, three names the
model has never defined, and Jinja renders an unknown attribute as the empty
string. A status-code assertion cannot tell the difference, so these tests
assert the content instead.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

import hop3.config
from hop3.config import HopConfig
from hop3.orm import reset_session_factory_cache
from hop3.server.asgi import create_app
from hop3.server.catalog import service as service_module
from hop3.server.catalog.service import CatalogService

if TYPE_CHECKING:
    from pathlib import Path

RECIPE = """
[metadata]
id = "gitea"
title = "Gitea"
version = "1.22.0"
description = "Self-hosted Git service"
homepage = "https://gitea.io/"
license = "MIT"
author = "Gitea"

[[addons]]
type = "postgres"
"""

OVERLAY = """
[catalog]
category = "Development"
tags = ["go", "git"]
memory = "512MB"
"""

SHOT = "gitea-01-login.png"
SHOT_URL = f"/dashboard/catalog/screenshots/gitea/{SHOT}"
# A one-pixel PNG, so the response body is a real image rather than a stub.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d76360000000020001e221bc330000000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def setup_secret_key():
    os.environ["HOP3_SECRET_KEY"] = "test-secret-key-for-integration-testing"
    yield
    os.environ.pop("HOP3_SECRET_KEY", None)


@pytest.fixture
def test_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOP3_DATABASE_URI", f"sqlite:///{tmp_path}/test.db")
    HopConfig.reset_instance()
    reset_session_factory_cache()
    HopConfig.set_instance(HopConfig(hop3_root=tmp_path))

    cat = tmp_path / "catalog"
    app_dir = cat / "gitea"
    (app_dir / "screenshots").mkdir(parents=True)
    (app_dir / "hop3.toml").write_text(RECIPE)
    (app_dir / "catalog.toml").write_text(OVERLAY)
    (app_dir / "readme.md").write_text("# Gitea\n\nA painless self-hosted forge.\n")
    (app_dir / "screenshots" / SHOT).write_bytes(PNG)

    monkeypatch.setattr(service_module, "_default_catalog_dir", lambda: cat)
    CatalogService.reset()
    CatalogService.get_instance().load(cat)
    monkeypatch.setattr(hop3.config, "HOP3_UNSAFE", True)  # bypass auth_guard

    client = TestClient(create_app())
    yield client

    HopConfig.reset_instance()
    reset_session_factory_cache()
    CatalogService.reset()


@pytest.fixture
def page(test_client) -> str:
    resp = test_client.get("/dashboard/catalog/apps/gitea")
    assert resp.status_code == 200
    return resp.content.decode()


@pytest.mark.parametrize(
    "shown",
    [
        "Self-hosted Git service",  # description
        "A painless self-hosted forge.",  # readme, the long form
        "512MB",  # memory, with its own unit
        "1.22.0",  # version
        "Development",  # category
        "postgres",  # the service it declares
        "https://gitea.io/",  # homepage, under the `website` field name
    ],
)
def test_the_detail_page_shows_what_the_entry_declares(page, shown):
    assert shown in page


def test_the_memory_row_does_not_invent_a_unit(page):
    """`memory` is "512MB" already; the row used to append " MB" to nothing."""
    assert "512MB MB" not in page


def test_screenshots_are_linked_through_the_serving_route(page):
    assert SHOT_URL in page


def test_a_linked_screenshot_is_actually_served(test_client, page):
    """The gallery is only real if the URL it builds returns the image."""
    assert SHOT_URL in page

    resp = test_client.get(SHOT_URL)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content == PNG


def test_the_fallback_icon_gets_a_background_color(test_client, tmp_path):
    """
    No icon file, so the card draws initials on a generated color.

    That color came from `initials_bg_color` — undefined, so every fallback
    icon rendered `background-color: ;` and the initials sat on nothing.
    """
    resp = test_client.get("/dashboard/catalog/apps/gitea")

    assert "background-color: #" in resp.content.decode()
