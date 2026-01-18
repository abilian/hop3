# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Marketplace controller for Hop3 web interface.

This controller handles all marketplace routes including:
- Marketplace home (featured apps, categories)
- App listing with search and filtering
- App detail pages
- Category browsing
- App installation
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Annotated

from litestar import Controller, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import File, Redirect, Template

from hop3.orm import App, EnvVar
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session
from hop3.server.marketplace import MarketplaceService

# ============================================================================
# Helper Functions
# ============================================================================


def _validate_app_name(app_name: str) -> list[str]:
    """Validate app name and return list of errors."""
    errors = []

    if not app_name:
        errors.append("App name is required")
        return errors

    if len(app_name) < 2:
        errors.append("App name must be at least 2 characters")

    if len(app_name) > 50:
        errors.append("App name must be at most 50 characters")

    if not re.match(r"^[a-z][a-z0-9-]*$", app_name):
        errors.append(
            "App name must start with a letter and contain only lowercase letters, "
            "numbers, and hyphens"
        )

    # Check for reserved names
    reserved = {"admin", "api", "app", "apps", "dashboard", "hop3", "static", "www"}
    if app_name in reserved:
        errors.append(f"'{app_name}' is a reserved name")

    return errors


def _check_app_exists(app_name: str) -> bool:
    """Check if an app with this name already exists."""
    with get_session() as db_session:
        existing = db_session.query(App).filter_by(name=app_name).first()
        return existing is not None


# ============================================================================
# Marketplace Controller
# ============================================================================


class MarketplaceController(Controller):
    """Marketplace web interface controller.

    Handles all marketplace routes for browsing and installing applications
    from the marketplace catalog.
    """

    path = "/dashboard/marketplace"
    guards = [auth_guard]  # noqa: RUF012 - base class defines as instance var

    # -------------------------------------------------------------------------
    # Marketplace Home
    # -------------------------------------------------------------------------

    @get("/", status_code=200, sync_to_thread=False)
    def marketplace_index(self) -> Template:
        """Display the marketplace home page.

        Shows featured apps and category overview.
        """
        service = MarketplaceService.get_instance()

        ctx = {
            "featured_apps": service.get_featured_apps(),
            "categories": service.list_categories(),
            "total_apps": len(service.list_apps()),
        }

        return Template(template_name="dashboard/marketplace/index.html", context=ctx)

    # -------------------------------------------------------------------------
    # Icon Serving
    # -------------------------------------------------------------------------

    @get("/icons/{app_id:str}", status_code=200, sync_to_thread=False, guards=[])
    def marketplace_icon(self, app_id: str) -> File | Redirect:
        """Serve app icon from the marketplace directory.

        Icons are stored in each app's directory as icon.webp or icon.png.
        """
        service = MarketplaceService.get_instance()
        apps_dir = service.apps_dir

        if not apps_dir:
            return Redirect(path="/static/favicon.png")

        # Check for icon files
        for ext in ["webp", "png", "svg", "jpg", "jpeg"]:
            icon_path = apps_dir / app_id / f"icon.{ext}"
            if icon_path.exists():
                media_type = {
                    "webp": "image/webp",
                    "png": "image/png",
                    "svg": "image/svg+xml",
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                }.get(ext, "image/png")
                return File(path=icon_path, media_type=media_type)

        # Fallback to default favicon
        return Redirect(path="/static/favicon.png")

    # -------------------------------------------------------------------------
    # All Apps Listing
    # -------------------------------------------------------------------------

    @get("/apps", status_code=200, sync_to_thread=False)
    def marketplace_list(self) -> Template:
        """Display all marketplace apps.

        Provides a searchable, filterable list of all available apps.
        """
        service = MarketplaceService.get_instance()

        # Convert apps to dicts for JSON serialization in Alpine.js
        apps_data = [app.to_dict() for app in service.list_apps()]

        ctx = {
            "apps": service.list_apps(),
            "apps_json": apps_data,
            "categories": service.list_categories(),
        }

        return Template(template_name="dashboard/marketplace/list.html", context=ctx)

    # -------------------------------------------------------------------------
    # App Detail
    # -------------------------------------------------------------------------

    @get("/apps/{app_id:str}", status_code=200, sync_to_thread=False)
    def marketplace_detail(self, app_id: str) -> Template | Redirect:
        """Display marketplace app detail page.

        Shows full app information and install form.
        """
        service = MarketplaceService.get_instance()
        app = service.get_app(app_id)

        if not app:
            return Redirect(path="/dashboard/marketplace")

        # Get similar apps (same category)
        similar_apps = []
        if app.category:
            category = next(
                (c for c in service.list_categories() if c.name == app.category), None
            )
            if category:
                similar_apps = [a for a in category.apps if a.id != app_id][:4]

        ctx = {
            "app": app,
            "similar_apps": similar_apps,
            "errors": [],
            "app_name": "",
        }

        return Template(template_name="dashboard/marketplace/detail.html", context=ctx)

    # -------------------------------------------------------------------------
    # Category Browsing
    # -------------------------------------------------------------------------

    @get("/category/{category_id:str}", status_code=200, sync_to_thread=False)
    def marketplace_category(self, category_id: str) -> Template | Redirect:
        """Display apps in a specific category."""
        service = MarketplaceService.get_instance()
        category = service.get_category(category_id)

        if not category:
            return Redirect(path="/dashboard/marketplace")

        ctx = {
            "category": category,
            "apps": category.apps,
            "categories": service.list_categories(),
        }

        return Template(
            template_name="dashboard/marketplace/category.html", context=ctx
        )

    # -------------------------------------------------------------------------
    # App Installation
    # -------------------------------------------------------------------------

    @post("/apps/{app_id:str}/install", status_code=303, sync_to_thread=True)
    def marketplace_install(
        self,
        app_id: str,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template | Redirect:
        """Install a marketplace app.

        Creates a new app from the marketplace template.
        """
        service = MarketplaceService.get_instance()
        marketplace_app = service.get_app(app_id)

        if not marketplace_app:
            return Redirect(path="/dashboard/marketplace")

        # Get and validate app name
        app_name = data.get("app_name", "").strip().lower()
        errors = _validate_app_name(app_name)

        # Check if app already exists
        if not errors and _check_app_exists(app_name):
            errors.append(f"An app named '{app_name}' already exists")

        if errors:
            return self._render_install_errors(
                service, marketplace_app, app_id, app_name, errors
            )

        # Create the app
        with get_session() as db_session:
            app = App(name=app_name)
            app.create()  # Creates directories

            _copy_marketplace_source(marketplace_app, app)
            _parse_and_add_env_vars(app, data.get("env_vars", ""))

            db_session.add(app)
            db_session.commit()

            # TODO: Trigger deployment (Phase 4)
            # app.deploy()

        return Redirect(
            path=f"/dashboard/apps/{app_name}?installed=true", status_code=303
        )

    def _render_install_errors(
        self,
        service: MarketplaceService,
        marketplace_app,
        app_id: str,
        app_name: str,
        errors: list[str],
    ) -> Template:
        """Re-render detail page with validation errors."""
        similar_apps = []
        if marketplace_app.category:
            category = next(
                (
                    c
                    for c in service.list_categories()
                    if c.name == marketplace_app.category
                ),
                None,
            )
            if category:
                similar_apps = [a for a in category.apps if a.id != app_id][:4]

        ctx = {
            "app": marketplace_app,
            "similar_apps": similar_apps,
            "errors": errors,
            "app_name": app_name,
        }
        return Template(template_name="dashboard/marketplace/detail.html", context=ctx)


def _copy_marketplace_source(marketplace_app, app: App) -> None:
    """Copy source files from marketplace app to new app."""
    if not marketplace_app.source_path:
        return

    src_path = Path(marketplace_app.source_path)
    if not src_path.exists():
        return

    dest_path = Path(app.src_path)
    dest_path.mkdir(parents=True, exist_ok=True)

    excluded_dirs = {"__pycache__", ".git"}
    for item in src_path.iterdir():
        if item.is_file():
            shutil.copy2(item, dest_path / item.name)
        elif item.is_dir() and item.name not in excluded_dirs:
            shutil.copytree(item, dest_path / item.name, dirs_exist_ok=True)


def _parse_and_add_env_vars(app: App, env_vars_str: str) -> None:
    """Parse environment variables string and add to app."""
    env_vars_str = env_vars_str.strip()
    if not env_vars_str:
        return

    for line in env_vars_str.split("\n"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key:
                app.env_vars.append(EnvVar(name=key, value=value))
