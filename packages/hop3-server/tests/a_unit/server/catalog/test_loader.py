# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the catalog TOML loader.

Locks down load_app (valid TOML -> populated CatalogApp; malformed or
missing -> None, never raising) and load_apps over a directory tree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.server.catalog.loader import load_app, load_apps

if TYPE_CHECKING:
    from pathlib import Path

VALID_TOML = """
[metadata]
id = "nextcloud"
title = "Nextcloud"
description = "Self-hosted file storage"
version = "1.2.3"
upstream_version = "28.0"
author = "Nextcloud GmbH"
website = "https://nextcloud.com"
license = "AGPL-3.0"
tags = ["storage", "sync"]

[resources]
memory = "128M"

[port]
web = 8080

[integration]
oauth = true

[[provider]]
name = "postgresql"

[[provider]]
name = "redis"
"""


def write_app(app_dir: Path, toml_text: str) -> Path:
    """Create an app directory containing a hop3.toml with the given text."""
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "hop3.toml").write_text(toml_text)
    return app_dir


class TestLoadApp:
    """load_app parses one app directory into a CatalogApp (or None)."""

    def test_valid_toml_populates_core_metadata(self, tmp_path: Path) -> None:
        app_dir = write_app(tmp_path / "nextcloud", VALID_TOML)

        app = load_app(app_dir)

        assert app is not None
        assert app.id == "nextcloud"
        assert app.title == "Nextcloud"
        assert app.description == "Self-hosted file storage"
        assert app.version == "1.2.3"
        assert app.upstream_version == "28.0"
        assert app.author == "Nextcloud GmbH"
        assert app.website == "https://nextcloud.com"
        assert app.license == "AGPL-3.0"
        assert app.tags == ["storage", "sync"]

    def test_parses_resources_port_and_integration(self, tmp_path: Path) -> None:
        app_dir = write_app(tmp_path / "nextcloud", VALID_TOML)

        app = load_app(app_dir)

        assert app is not None
        assert app.memory == "128M"
        assert app.port == 8080
        assert app.integrations == {"oauth": True}

    def test_collects_provider_names(self, tmp_path: Path) -> None:
        app_dir = write_app(tmp_path / "nextcloud", VALID_TOML)

        app = load_app(app_dir)

        assert app is not None
        assert app.providers == ["postgresql", "redis"]

    def test_computes_resource_tier_from_memory(self, tmp_path: Path) -> None:
        # 128M <= 256 -> "light" per CatalogApp.compute_resource_tier.
        app_dir = write_app(tmp_path / "nextcloud", VALID_TOML)

        app = load_app(app_dir)

        assert app is not None
        assert app.resource_tier == "light"

    def test_records_source_path(self, tmp_path: Path) -> None:
        app_dir = write_app(tmp_path / "nextcloud", VALID_TOML)

        app = load_app(app_dir)

        assert app is not None
        assert app.source_path == str(app_dir)

    def test_missing_metadata_falls_back_to_directory_name(
        self, tmp_path: Path
    ) -> None:
        # No [metadata]: id from dir name, title from dir name title-cased.
        app_dir = write_app(tmp_path / "my-app", "[resources]\nmemory = '512M'\n")

        app = load_app(app_dir)

        assert app is not None
        assert app.id == "my-app"
        assert app.title == "My-App"
        assert app.tags == []

    def test_renders_readme_html_and_strips_first_h1(self, tmp_path: Path) -> None:
        app_dir = write_app(tmp_path / "doc", VALID_TOML)
        (app_dir / "readme.md").write_text("# Title\n\nSome **body** text.\n")

        app = load_app(app_dir)

        assert app is not None
        assert app.readme.startswith("# Title")
        # The leading H1 is stripped (shown in the page header instead).
        assert "<h1" not in app.readme_html
        assert "<strong>body</strong>" in app.readme_html

    def test_missing_toml_returns_none(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        assert load_app(empty_dir) is None

    def test_malformed_toml_returns_none_without_raising(self, tmp_path: Path) -> None:
        app_dir = write_app(tmp_path / "broken", "this is = = not valid toml [[[")

        assert load_app(app_dir) is None


class TestLoadApps:
    """load_apps walks a directory tree, skipping non-apps and dotfiles."""

    def test_loads_every_valid_app(self, tmp_path: Path) -> None:
        write_app(tmp_path / "a", VALID_TOML)
        write_app(tmp_path / "b", VALID_TOML)

        apps = load_apps(tmp_path)

        assert {a.id for a in apps} == {"nextcloud"}  # both share the id
        assert len(apps) == 2

    def test_results_sorted_by_directory_name(self, tmp_path: Path) -> None:
        write_app(tmp_path / "zoo", "[metadata]\nid = 'zoo'\n")
        write_app(tmp_path / "ant", "[metadata]\nid = 'ant'\n")

        apps = load_apps(tmp_path)

        assert [a.id for a in apps] == ["ant", "zoo"]

    def test_skips_directories_without_toml(self, tmp_path: Path) -> None:
        write_app(tmp_path / "good", VALID_TOML)
        (tmp_path / "no-toml").mkdir()

        apps = load_apps(tmp_path)

        assert len(apps) == 1

    def test_skips_dot_prefixed_directories(self, tmp_path: Path) -> None:
        write_app(tmp_path / ".hidden", VALID_TOML)
        write_app(tmp_path / "visible", VALID_TOML)

        apps = load_apps(tmp_path)

        assert len(apps) == 1
        assert apps[0].source_path == str(tmp_path / "visible")

    def test_skips_plain_files_at_top_level(self, tmp_path: Path) -> None:
        write_app(tmp_path / "app", VALID_TOML)
        (tmp_path / "README").write_text("not a dir")

        apps = load_apps(tmp_path)

        assert len(apps) == 1

    def test_missing_directory_returns_empty_list(self, tmp_path: Path) -> None:
        assert load_apps(tmp_path / "does-not-exist") == []

    def test_sets_icon_url_when_icon_present(self, tmp_path: Path) -> None:
        app_dir = write_app(tmp_path / "iconned", VALID_TOML)
        (app_dir / "icon.png").write_bytes(b"\x89PNG")

        apps = load_apps(tmp_path)

        assert apps[0].icon_url == "/dashboard/catalog/icons/nextcloud"

    def test_leaves_icon_url_none_without_icon(self, tmp_path: Path) -> None:
        write_app(tmp_path / "plain", VALID_TOML)

        apps = load_apps(tmp_path)

        assert apps[0].icon_url is None
