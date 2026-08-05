# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
security-model.md §3.7: no cookie-authenticated route changes state on a GET.

hop3-server ships no CSRF middleware. What stands in for one is `samesite=lax`
plus the fact that every dangerous mutation is a POST: `lax` withholds the auth
cookie on a cross-site POST but sends it on a cross-site GET, so a single
state-changing GET is enough to make the whole argument false. `GET
/auth/logout` was exactly that exception, and it survived from May 2026 to
August 2026 because the invariant lived in a documentation section rather than
in anything that ran.

Every GET the application serves is therefore listed below and asserted to be
a read. Adding a route makes this test fail until someone writes its path into
the list, which is the moment to ask whether it mutates.
"""

from __future__ import annotations

import pytest

from hop3.server.asgi import create_app

# Prefixes served by the framework, not by our controllers: static assets and
# the generated OpenAPI documentation. Neither touches application state.
FRAMEWORK_PREFIXES = ("/static", "/schema")

# Every GET route the application serves. Each one is a read: it renders a
# page, streams a log, or returns a document. NOTHING HERE MAY MUTATE STATE.
#
# `/auth/magic/{token}` deserves a note, because it is the closest call: it
# consumes a single-use token, which is a write. It stays a GET because a magic
# *link* has to work when pasted into a browser's address bar. It is safe
# against the CSRF concern for a different reason -- an attacker who can make
# your browser fetch a magic link already holds the token, so nothing is gained
# by the forgery. See report-2026-07-29.md F6 for the consumption-order
# question, which is separate and still open.
READ_ONLY_GET_ROUTES = frozenset({
    "/",
    "/api/stream/{stream_id:str}",
    "/api/stream/{stream_id:str}/status",
    "/auth/login",
    "/auth/magic/{token:str}",
    "/auth/profile",
    "/dashboard",
    "/dashboard/addons",
    "/dashboard/addons/{addon_name:str}",
    "/dashboard/apps/new",
    "/dashboard/apps/{app_name:str}",
    "/dashboard/apps/{app_name:str}/credentials",
    "/dashboard/apps/{app_name:str}/env",
    "/dashboard/apps/{app_name:str}/logs",
    "/dashboard/apps/{app_name:str}/logs/download",
    "/dashboard/apps/{app_name:str}/logs/stream",
    "/dashboard/apps/{app_name:str}/status",
    "/dashboard/backups",
    "/dashboard/backups/{backup_id:str}/info",
    "/dashboard/catalog",
    "/dashboard/catalog/apps",
    "/dashboard/catalog/apps/{app_id:str}",
    "/dashboard/catalog/category/{category_id:str}",
    "/dashboard/catalog/icons/{app_id:str}",
    "/dashboard/catalog/screenshots/{app_id:str}/{filename:str}",
    "/dashboard/certificates",
})


@pytest.fixture(scope="module")
def get_routes() -> frozenset[str]:
    """Paths the application answers on GET, excluding framework routes."""
    app = create_app()
    return frozenset(
        route.path
        for route in app.routes
        if "GET" in (getattr(route, "methods", None) or ())
        and not route.path.startswith(FRAMEWORK_PREFIXES)
    )


def test_every_get_route_is_a_declared_read(get_routes: frozenset[str]) -> None:
    """A new GET route must be declared a read before it can ship."""
    undeclared = get_routes - READ_ONLY_GET_ROUTES
    assert not undeclared, (
        f"GET routes not declared read-only: {sorted(undeclared)}. "
        "hop3-server has no CSRF token; `samesite=lax` sends the auth cookie "
        "on cross-site GETs, so a GET that mutates state is CSRF-able. Make it "
        "a POST, or add it to READ_ONLY_GET_ROUTES if it truly only reads."
    )


def test_the_route_list_has_not_gone_stale(get_routes: frozenset[str]) -> None:
    """A list naming routes that no longer exist stops being evidence."""
    departed = READ_ONLY_GET_ROUTES - get_routes
    assert not departed, (
        f"READ_ONLY_GET_ROUTES names routes the app no longer serves: "
        f"{sorted(departed)}. Remove them."
    )


def test_logout_is_not_reachable_by_get(get_routes: frozenset[str]) -> None:
    """Regression: the exception that made the POST-only argument untrue."""
    assert "/auth/logout" not in get_routes
