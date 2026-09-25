# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Every route the server answers names the lowest role that may use it (ADR 061).

The dashboard's counterpart of ``commands/command_roles.toml``: the whole web
policy in one reviewable table. A page that reads state needs ``viewer``; one
that shows a secret (environment values, credentials, connection details,
logs) or changes anything needs ``deployer``. ``/rpc`` is public here because
the dispatcher checks each command's own role. Adding a route makes this test
fail until someone writes its role below, on purpose.
"""

from __future__ import annotations

import pytest

from hop3.core.roles import Role
from hop3.server.asgi import create_app
from hop3.server.guards import RoleGuard

FRAMEWORK_PREFIXES = ("/static", "/schema")

EXPECTED = {
    ("GET", "/"): "public",
    ("POST", "/rpc"): "public",
    ("GET", "/auth/login"): "public",
    ("POST", "/auth/login"): "public",
    ("POST", "/auth/logout"): "public",
    ("GET", "/auth/magic/{token:str}"): "public",
    ("GET", "/auth/profile"): "member",
    # The access gate decides per request, from the gate cookie (ADR 062).
    ("GET", "/auth/check"): "public",
    ("GET", "/_hop3/auth/callback"): "public",
    ("GET", "/api/stream/{stream_id:str}"): "deployer",
    ("GET", "/api/stream/{stream_id:str}/status"): "deployer",
    ("GET", "/dashboard"): "viewer",
    ("GET", "/dashboard/addons"): "viewer",
    ("GET", "/dashboard/addons/{addon_name:str}"): "deployer",
    ("GET", "/dashboard/apps/new"): "deployer",
    ("POST", "/dashboard/apps/new"): "deployer",
    ("GET", "/dashboard/apps/{app_name:str}"): "viewer",
    ("GET", "/dashboard/apps/{app_name:str}/credentials"): "deployer",
    ("GET", "/dashboard/apps/{app_name:str}/env"): "deployer",
    ("GET", "/dashboard/apps/{app_name:str}/logs"): "deployer",
    ("GET", "/dashboard/apps/{app_name:str}/logs/download"): "deployer",
    ("GET", "/dashboard/apps/{app_name:str}/logs/stream"): "deployer",
    ("GET", "/dashboard/apps/{app_name:str}/status"): "viewer",
    ("POST", "/dashboard/apps/{app_name:str}/backup"): "deployer",
    ("POST", "/dashboard/apps/{app_name:str}/restart"): "deployer",
    ("POST", "/dashboard/apps/{app_name:str}/stop"): "deployer",
    ("GET", "/dashboard/backups"): "viewer",
    ("GET", "/dashboard/backups/{backup_id:str}/info"): "viewer",
    ("POST", "/dashboard/backups/{backup_id:str}/delete"): "deployer",
    ("POST", "/dashboard/backups/{backup_id:str}/restore"): "deployer",
    ("GET", "/dashboard/catalog"): "viewer",
    ("GET", "/dashboard/catalog/apps"): "viewer",
    ("GET", "/dashboard/catalog/apps/{app_id:str}"): "viewer",
    ("POST", "/dashboard/catalog/apps/{app_id:str}/install"): "deployer",
    ("GET", "/dashboard/catalog/category/{category_id:str}"): "viewer",
    ("GET", "/dashboard/catalog/icons/{app_id:str}"): "viewer",
    ("GET", "/dashboard/catalog/screenshots/{app_id:str}/{filename:str}"): "viewer",
    ("GET", "/dashboard/certificates"): "viewer",
}


@pytest.fixture(scope="module")
def served() -> dict[tuple[str, str], str]:
    """(method, path) -> the strictest role its guards require, or "public"."""
    order = list(Role)
    roles: dict[tuple[str, str], str] = {}
    for route in create_app().routes:
        if route.path.startswith(FRAMEWORK_PREFIXES):
            continue
        for handler in getattr(route, "route_handlers", ()):
            # Litestar wraps each guard; `func` is the guard itself.
            guards = [getattr(g, "func", g) for g in handler.resolve_guards()]
            required = [g.required for g in guards if isinstance(g, RoleGuard)]
            role = max(required, key=order.index).value if required else "public"
            for method in handler.http_methods:
                if method != "OPTIONS":
                    roles[method, route.path] = role
    return roles


def test_every_route_has_its_role_in_the_table(served):
    assert sorted(served.keys() - EXPECTED.keys()) == []
    assert sorted(EXPECTED.keys() - served.keys()) == []


@pytest.mark.parametrize(("route", "role"), sorted(EXPECTED.items()))
def test_each_route_requires_its_role(served, route, role):
    assert served[route] == role
