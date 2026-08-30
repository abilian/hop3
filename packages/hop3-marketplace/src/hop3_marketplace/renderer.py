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
    # Listings show applications, not recipes: an application packaged three
    # ways is one entry with a build-path choice on its page, not three cards
    # differing by a suffix. Every recipe still gets a page rendered below, so
    # a variant stays linkable and installable by id.
    applications = [app for app in apps if app.is_default_variant]
    featured_apps = [app for app in applications if app.featured]
    recent_apps = applications[-6:] if len(applications) > 6 else applications

    common = {"base_url": ""}

    render_page(
        env,
        "index.html",
        output_dir / "index.html",
        apps=applications,
        categories=categories,
        featured_apps=featured_apps,
        recent_apps=recent_apps,
        **common,
    )
    render_page(
        env,
        "apps/list.html",
        output_dir / "apps" / "index.html",
        apps=applications,
        categories=categories,
        **common,
    )
    # A page per recipe, so a variant remains linkable; the build paths of the
    # application it belongs to are offered on each of them.
    by_application: dict[str, list[CatalogApp]] = {}
    for app in apps:
        by_application.setdefault(app.variant_of or app.id, []).append(app)
    for app in apps:
        siblings = by_application.get(app.variant_of or app.id, [])
        render_page(
            env,
            "apps/detail.html",
            output_dir / "apps" / app.id / "index.html",
            app=app,
            similar_apps=get_similar_apps(app, applications),
            variants=sorted(siblings, key=lambda a: (bool(a.variant_of), a.build_path)),
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
    """Write the client-side search index, over applications."""
    apps = [app for app in apps if app.is_default_variant]
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
