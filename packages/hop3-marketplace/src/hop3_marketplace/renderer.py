# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Render catalog apps to a static site with Jinja2."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from hop3.server.catalog.models import CatalogApp, Category, Tag

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_jinja_env(templates_dir: Path = TEMPLATES_DIR) -> Environment:
    """Create the Jinja environment, with autoescaping on."""
    return Environment(loader=FileSystemLoader(templates_dir), autoescape=True)


def render_page(
    env: Environment, template_name: str, output_path: Path, **context: object
) -> None:
    """Render one template to one file."""
    html = env.get_template(template_name).render(**context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)


def get_similar_apps(
    app: CatalogApp, all_apps: list[CatalogApp], limit: int = 4
) -> list[CatalogApp]:
    """Other apps in the same category."""
    similar = [a for a in all_apps if a.category == app.category and a.id != app.id]
    return similar[:limit]


def render_site(
    apps: list[CatalogApp],
    categories: list[Category],
    tags: list[Tag],
    output_dir: Path,
    templates_dir: Path = TEMPLATES_DIR,
) -> None:
    """Render the whole site into ``output_dir``, which is replaced."""
    env = create_jinja_env(templates_dir)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Featured comes from each app's `[catalog].featured`, not a list kept here:
    # a curated list in the renderer goes stale silently, and did — it named
    # twelve apps, ten of which the catalog does not contain.
    featured_apps = [app for app in apps if app.featured]
    recent_apps = apps[-6:] if len(apps) > 6 else apps

    common = {"base_url": ""}

    render_page(
        env,
        "index.html",
        output_dir / "index.html",
        apps=apps,
        categories=categories,
        featured_apps=featured_apps,
        recent_apps=recent_apps,
        **common,
    )
    render_page(
        env,
        "apps/list.html",
        output_dir / "apps" / "index.html",
        apps=apps,
        categories=categories,
        **common,
    )
    for app in apps:
        render_page(
            env,
            "apps/detail.html",
            output_dir / "apps" / app.id / "index.html",
            app=app,
            similar_apps=get_similar_apps(app, apps),
            **common,
        )
    for category in categories:
        render_page(
            env,
            "category.html",
            output_dir / "category" / category.id / "index.html",
            category=category,
            **common,
        )
    for tag in tags:
        render_page(
            env,
            "tag.html",
            output_dir / "tag" / tag.id / "index.html",
            tag=tag,
            **common,
        )
    render_page(env, "about.html", output_dir / "about" / "index.html", **common)


def generate_search_index(apps: list[CatalogApp], output_path: Path) -> None:
    """Write the client-side search index."""
    index = [
        {
            "id": app.id,
            "title": app.title,
            "description": app.description,
            "tags": app.tags,
            "author": app.author,
            "category": app.category,
            "url": f"/apps/{app.id}/",
        }
        for app in apps
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index, indent=2))


def copy_static(output_dir: Path, static_dir: Path = STATIC_DIR) -> None:
    """Copy CSS and JS into ``output_dir/assets``."""
    assets_dir = output_dir / "assets"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    shutil.copytree(static_dir, assets_dir)
