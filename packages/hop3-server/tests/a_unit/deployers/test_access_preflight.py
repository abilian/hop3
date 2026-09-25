# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A deploy with ``[access] require = "auth"`` checks the gate can work (ADR 062 §5).

Each missing precondition aborts before the build with the reason. A gate
that passes is recorded on the app, where the proxy's check reads it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3 import config
from hop3.core.roles import Role
from hop3.deployers import access
from hop3.lib.console import Abort
from hop3.orm import App
from hop3.project.hop3_config import Hop3Config

GATED = {"access": {"require": "auth", "role": "viewer", "public-paths": ["/hook"]}}


@pytest.fixture(autouse=True)
def server(monkeypatch):
    monkeypatch.setattr(
        type(config.config), "ADMIN_DOMAIN", property(lambda _self: "admin.example.org")
    )
    monkeypatch.setattr(config, "HOP3_PROXY_TYPE", "nginx")


def deploy(data, *, host="notes.example.org"):
    app = App(name="notes")
    app.get_runtime_env = lambda: {"HOST_NAME": host}
    app_config = SimpleNamespace(hop3_config=Hop3Config(_data=data))
    access.configure_access_preflight(app, app_config, None)
    return app


def test_a_gate_is_recorded_on_the_app():
    app = deploy(GATED)

    assert (app.access_role, app.access_public_paths) == (Role.VIEWER, ["/hook"])


def test_an_app_without_a_gate_records_none():
    app = deploy({})

    assert (app.access_role, app.access_public_paths) == (None, [])


def test_no_admin_domain(monkeypatch):
    monkeypatch.setattr(type(config.config), "ADMIN_DOMAIN", property(lambda _s: ""))

    with pytest.raises(Abort, match="no admin domain is set"):
        deploy(GATED)


@pytest.mark.parametrize("host", ["", "_"])
def test_no_hostname(host):
    with pytest.raises(Abort, match="the app has no hostname"):
        deploy(GATED, host=host)


def test_plain_http():
    with pytest.raises(Abort, match="allow-http serves the app over plain HTTP"):
        deploy({**GATED, "deploy": {"allow-http": True}})


def test_a_proxy_without_the_gate(monkeypatch):
    monkeypatch.setattr(
        access, "get_proxy_class", lambda: SimpleNamespace(gates_access=False)
    )

    with pytest.raises(Abort, match=r"proxy \(nginx\) cannot enforce it"):
        deploy(GATED)
