# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""TOML loader for catalog app metadata."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import markdown
import nh3
import tomllib

from .models import CatalogApp
from .policy import CatalogSpecError, validate_catalog_spec

logger = logging.getLogger(__name__)

# Markdown converter instance
_md = markdown.Markdown(extensions=["extra", "toc"])

# Pattern to match and remove the first H1 tag
_h1_pattern = re.compile(r"<h1[^>]*>.*?</h1>\s*", re.IGNORECASE | re.DOTALL)

# Catalog readmes are untrusted (the catalog is fetched from a remote source).
# Raster icon extensions only — never serve SVG, which is an XSS vector when
# rendered inline (ADR 049 F6). The loader/render path never emits raw SVG.
_ICON_EXTENSIONS = ("webp", "png", "jpg", "jpeg")

#: Where an app's captures live inside its own catalog directory.
_SCREENSHOTS_DIR = "screenshots"


def find_screenshots(app: CatalogApp) -> list[Path]:
    """
    Return the app's screenshot files, in filename order.

    Same containment rule as :func:`find_icon`: resolved inside the app's own
    verified directory, raster only, so a crafted catalog cannot point the
    render path at an SVG or at something outside the app.

    Ordering is by filename because the captures are named for their sequence
    (``…-01-login.png`` then ``…-02-signed-in.png``), so sorting shows the
    sign-in page before the page behind it.
    """
    if not app.source_path:
        return []
    base = Path(app.source_path).resolve()
    shots_dir = (base / _SCREENSHOTS_DIR).resolve()
    if shots_dir.parent != base or not shots_dir.is_dir():
        return []

    found = [
        path
        for path in sorted(shots_dir.iterdir())
        if path.suffix.lstrip(".").lower() in _ICON_EXTENSIONS
        and path.resolve().parent == shots_dir
        and path.is_file()
    ]
    return found


def find_icon(app: CatalogApp) -> Path | None:
    """
    Return the app's icon file inside its own source dir, or None.

    Resolves only within ``app.source_path`` (a verified catalog dir) and never
    returns an SVG, so the public icon route cannot serve an XSS payload or be
    tricked into path traversal (ADR 049 F6).
    """
    if not app.source_path:
        return None
    base = Path(app.source_path).resolve()
    for ext in _ICON_EXTENSIONS:
        candidate = (base / f"icon.{ext}").resolve()
        if candidate.parent == base and candidate.is_file():
            return candidate
    return None


def load_app(app_dir: Path) -> CatalogApp | None:
    """Load a single app from its directory."""
    toml_path = app_dir / "hop3.toml"
    if not toml_path.exists():
        return None

    try:
        with Path(toml_path).open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(f"  Warning: Skipping {app_dir.name} - TOML parse error: {e}")
        return None

    metadata = data.get("metadata", {})
    # Coexistence gate (ADR 049 F7): refuse a spec that would hijack shared proxy
    # routing. Raised here, handled (excluded + logged loudly) by the callers.
    validate_catalog_spec(data, metadata.get("id", app_dir.name))

    resources = data.get("resources", {})
    port_config = data.get("port", {})
    integration = data.get("integration", {})

    # Services the app declares. `[[addons]]` is what recipes actually use;
    # `[[provider]]` is the older spelling and no recipe in the catalog carries
    # one, which is why every app displayed "no services" until 0.7.2.
    providers = [
        addon["type"] for addon in data.get("addons", []) if addon.get("type")
    ] or [
        provider["name"] for provider in data.get("provider", []) if "name" in provider
    ]

    overlay = _load_catalog_overlay(app_dir)

    app = CatalogApp(
        id=metadata.get("id", app_dir.name),
        title=metadata.get("title", app_dir.name.title()),
        description=metadata.get("description", ""),
        version=metadata.get("version", ""),
        upstream_version=metadata.get("upstream_version"),
        author=metadata.get("author", ""),
        # Recipes declare `homepage`; `website` is the older key.
        website=metadata.get("homepage") or metadata.get("website", ""),
        license=metadata.get("license", ""),
        # The overlay owns display tags. Falling back to the recipe's own
        # `categories` keeps an app that has no overlay out of the "no tags at
        # all" state that made every card look identical.
        tags=overlay.get("tags")
        or metadata.get("tags")
        or metadata.get("categories", []),
        memory=overlay.get("memory") or resources.get("memory"),
        port=port_config.get("web"),
        integrations=integration,
        providers=providers,
        featured=bool(overlay.get("featured", False)),
        license_note=overlay.get("license_note", ""),
        screenshots=overlay.get("screenshots", []),
        category=overlay.get("category", ""),
        source_path=str(app_dir),
    )

    # Compute resource tier
    app.resource_tier = app.compute_resource_tier()

    # An app that declares no screenshots gets the ones it ships. The overlay
    # stays authoritative when set (an app may want a subset, or a different
    # order), but the default must not be a list in 55 files mirroring 55
    # directories: every entry said `screenshots = []` while shipping captures.
    if not app.screenshots:
        app.screenshots = [
            f"{_SCREENSHOTS_DIR}/{path.name}" for path in find_screenshots(app)
        ]

    # Load readme if exists
    readme_path = app_dir / "readme.md"
    if readme_path.exists():
        app.readme = readme_path.read_text()
        _md.reset()
        html = _md.convert(app.readme)
        # Remove the first H1 (title is already shown in page header)
        html = _h1_pattern.sub("", html, count=1)
        # The readme is untrusted catalog content — sanitize to an allowlist so a
        # crafted readme can't inject script/onerror/etc. into the dashboard.
        app.readme_html = nh3.clean(html)

    return app


def _load_catalog_overlay(app_dir: Path) -> dict:
    """
    Read the ``[catalog]`` table from the app's optional ``catalog.toml``.

    The overlay carries everything that is presentation rather than deployment:
    category, tags, memory, featured, screenshots, license_note. It is optional,
    and an app without one still loads from its recipe alone.

    A *malformed* one is a different matter and raises. Rendering an app with
    silently missing metadata is how the dashboard came to show 55 identical
    cards in a single category, and the publish-time gate is where a broken
    overlay should be caught — not in the reader, by degrading quietly.
    """
    overlay_path = app_dir / "catalog.toml"
    if not overlay_path.exists():
        return {}

    try:
        with overlay_path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        msg = f"{overlay_path}: malformed catalog.toml: {e}"
        raise CatalogSpecError(msg) from e

    return data.get("catalog", {})


def _attach_icon(app: CatalogApp, app_dir: Path) -> None:
    """Set the catalog icon URL if the app ships an icon file."""
    icon_path = app_dir / "icon.webp"
    if not icon_path.exists():
        icon_path = app_dir / "icon.png"
    if icon_path.exists():
        app.icon_url = f"/dashboard/catalog/icons/{app.id}"


def load_apps(apps_dir: Path) -> list[CatalogApp]:
    """
    Load all apps by scanning ``apps_dir`` (dev/local fallback).

    Production loads via :func:`load_apps_from_index` so only the signed,
    verified file set is executed (ADR 049 F1). This unsigned scan is the
    fallback for a local checkout that has no ``index.json``.
    """
    apps: list[CatalogApp] = []

    if not apps_dir.exists():
        return apps

    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        if app_dir.name.startswith("."):
            continue

        try:
            app = load_app(app_dir)
        except CatalogSpecError:
            logger.exception("Excluding catalog app %r from the catalog", app_dir.name)
            continue
        if app:
            _attach_icon(app, app_dir)
            apps.append(app)

    return apps


def load_apps_from_index(apps_dir: Path, index: dict) -> list[CatalogApp]:
    """
    Load only the app directories named in the (verified) ``index.json``.

    Drives off the signed index rather than ``iterdir()`` so a stray/leftover
    directory on disk can never be loaded or installed (ADR 049 F1).
    """
    seen: set[str] = set()
    app_dirs: list[str] = []
    for app in index.get("apps", []):
        for entry in app.get("files", []):
            top = entry["path"].split("/", 1)[0]
            if top and top not in seen:
                seen.add(top)
                app_dirs.append(top)

    apps: list[CatalogApp] = []
    for name in app_dirs:
        app_dir = apps_dir / name
        try:
            app = load_app(app_dir)
        except CatalogSpecError:
            logger.exception("Excluding catalog app %r from the catalog", name)
            continue
        if app:
            _attach_icon(app, app_dir)
            apps.append(app)
    return apps
