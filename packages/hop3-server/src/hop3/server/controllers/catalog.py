# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Catalog controller for Hop3 web interface.

This controller handles all catalog routes including:
- Catalog home (featured apps, categories)
- App listing with search and filtering
- App detail pages
- Category browsing
- App installation
"""

from __future__ import annotations

from typing import Annotated

from litestar import Controller, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body, FromPath
from litestar.response import File, Redirect, Template

from hop3.commands._deploy import deploy_app_streaming
from hop3.server.catalog import CatalogService
from hop3.server.catalog.install import CatalogInstallError, stage_catalog_app
from hop3.server.catalog.loader import find_icon
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session

# ============================================================================
# Catalog Controller
# ============================================================================


class CatalogController(Controller):
    """Catalog web interface controller.

    Handles all catalog routes for browsing and installing applications
    from the catalog.
    """

    path = "/dashboard/catalog"
    guards = [auth_guard]  # ruff:ignore[mutable-class-default] - base class defines as instance var

    # -------------------------------------------------------------------------
    # Catalog Home
    # -------------------------------------------------------------------------

    @get("/", status_code=200, sync_to_thread=False)
    def catalog_index(self) -> Template:
        """Display the catalog home page.

        Shows featured apps and category overview.
        """
        service = CatalogService.get_instance()

        ctx = {
            "catalog_available": service.is_available(),
            "featured_apps": service.get_featured_apps(),
            "categories": service.list_categories(),
            "total_apps": len(service.list_apps()),
        }

        return Template(template_name="dashboard/catalog/index.html", context=ctx)

    # -------------------------------------------------------------------------
    # Icon Serving
    # -------------------------------------------------------------------------

    # AUDIT: guards=[] is intentional — the catalog is
    # public by design. See notes/security.md §3.6.1.
    @get("/icons/{app_id:str}", status_code=200, sync_to_thread=False, guards=[])
    def catalog_icon(self, app_id: FromPath[str]) -> File | Redirect:
        """Serve a catalog app's icon (raster only; never SVG — ADR 049 F6).

        The icon is resolved from the *verified* app's own source directory via
        ``find_icon``, never by joining the URL ``app_id`` onto a path, so a
        crafted id cannot traverse the filesystem or serve an SVG XSS payload.
        """
        service = CatalogService.get_instance()
        app = service.get_app(app_id)
        if app is None:
            return Redirect(path="/static/favicon.png")

        icon_path = find_icon(app)
        if icon_path is None:
            return Redirect(path="/static/favicon.png")

        suffix = icon_path.suffix.lower()
        media_type = {".webp": "image/webp", ".png": "image/png"}.get(
            suffix, "image/jpeg"
        )
        # nosniff so a mislabeled file can't be reinterpreted as active content.
        return File(
            path=icon_path,
            media_type=media_type,
            headers={"X-Content-Type-Options": "nosniff"},
        )

    # -------------------------------------------------------------------------
    # All Apps Listing
    # -------------------------------------------------------------------------

    @get("/apps", status_code=200, sync_to_thread=False)
    def catalog_list(self) -> Template:
        """Display all catalog apps.

        Provides a searchable, filterable list of all available apps.
        """
        service = CatalogService.get_instance()

        # Convert apps to dicts for JSON serialization in Alpine.js
        apps_data = [app.to_dict() for app in service.list_apps()]

        ctx = {
            "apps": service.list_apps(),
            "apps_json": apps_data,
            "categories": service.list_categories(),
        }

        return Template(template_name="dashboard/catalog/list.html", context=ctx)

    # -------------------------------------------------------------------------
    # App Detail
    # -------------------------------------------------------------------------

    @get("/apps/{app_id:str}", status_code=200, sync_to_thread=False)
    def catalog_detail(self, app_id: FromPath[str]) -> Template | Redirect:
        """Display catalog app detail page.

        Shows full app information and install form.
        """
        service = CatalogService.get_instance()
        app = service.get_app(app_id)

        if not app:
            return Redirect(path="/dashboard/catalog")

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
            "domain": "",
        }

        return Template(template_name="dashboard/catalog/detail.html", context=ctx)

    # -------------------------------------------------------------------------
    # Category Browsing
    # -------------------------------------------------------------------------

    @get("/category/{category_id:str}", status_code=200, sync_to_thread=False)
    def catalog_category(self, category_id: FromPath[str]) -> Template | Redirect:
        """Display apps in a specific category."""
        service = CatalogService.get_instance()
        category = service.get_category(category_id)

        if not category:
            return Redirect(path="/dashboard/catalog")

        ctx = {
            "category": category,
            "apps": category.apps,
            "categories": service.list_categories(),
        }

        return Template(template_name="dashboard/catalog/category.html", context=ctx)

    # -------------------------------------------------------------------------
    # App Installation
    # -------------------------------------------------------------------------

    @post("/apps/{app_id:str}/install", status_code=303, sync_to_thread=True)
    def catalog_install(
        self,
        app_id: FromPath[str],
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template | Redirect:
        """Install a catalog app: stage its recipe, then start a live deploy.

        Staging (create app, copy the verified recipe, set env) is shared with
        the ``hop3 catalog install`` CLI via ``stage_catalog_app``. The build and
        run then happen in the background through the same streaming path as
        ``hop3 deploy`` — we do NOT claim success here: the app page reflects the
        real run state (DEPLOYING → RUNNING/FAILED), and a failed deploy alerts
        the operator (ADR 054).
        """
        service = CatalogService.get_instance()
        catalog_app = service.get_app(app_id)
        if not catalog_app:
            return Redirect(path="/dashboard/catalog")

        app_name = data.get("app_name", "").strip().lower()
        env_vars = data.get("env_vars", "")
        domain = data.get("domain", "").strip()
        try:
            with get_session() as db_session:
                app = stage_catalog_app(
                    app_id, app_name, env_vars, db_session, domain=domain
                )
                app_pk = app.id
        except CatalogInstallError as exc:
            return self._render_install_errors(
                service, catalog_app, app_id, app_name, exc.errors, domain=domain
            )

        deploy_app_streaming(app_name, app_pk)
        return Redirect(
            path=f"/dashboard/apps/{app_name}?deploying=true", status_code=303
        )

    def _render_install_errors(
        self,
        service: CatalogService,
        catalog_app,
        app_id: str,
        app_name: str,
        errors: list[str],
        domain: str = "",
    ) -> Template:
        """Re-render detail page with validation errors."""
        similar_apps = []
        if catalog_app.category:
            category = next(
                (
                    c
                    for c in service.list_categories()
                    if c.name == catalog_app.category
                ),
                None,
            )
            if category:
                similar_apps = [a for a in category.apps if a.id != app_id][:4]

        ctx = {
            "app": catalog_app,
            "similar_apps": similar_apps,
            "errors": errors,
            "app_name": app_name,
            "domain": domain,
        }
        return Template(template_name="dashboard/catalog/detail.html", context=ctx)
