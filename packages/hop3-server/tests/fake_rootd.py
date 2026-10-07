# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Stand-ins for hop3-rootd, Mailpit and the network, for in-process tests.

Production code used to skip its rootd calls, the email sink check and the
port-25 probe when it saw `PYTEST_CURRENT_TEST`: code deciding what to do by asking whether it
was under test. The fake is stated here instead, registered for every test
of this package by its conftest (the e2e layer reaches the real daemon in a
container, never these modules in-process), where a test can see it and
replace it.
"""

from __future__ import annotations

from typing import ClassVar, Self

import pytest

from hop3.commands import app as app_commands
from hop3.platform import certificates
from hop3.plugins.email import onramp, server_cli
from hop3.plugins.proxy.caddy import _setup as caddy_setup
from hop3.plugins.proxy.nginx import _setup as nginx_setup
from hop3.plugins.proxy.traefik import _setup as traefik_setup

#: The modules that skipped their rootd call under pytest, by the name each
#: imported. Not `hop3.lib.rootd` itself: the rootd client has tests of its own.
_CLIENT_USERS = (onramp, nginx_setup, app_commands, certificates)
_RELOAD_USERS = (caddy_setup, traefik_setup)


class FakeRootdClient:
    """Every op succeeds, and is recorded; nginx's config always validates."""

    calls: ClassVar[list[tuple[str, dict[str, object]]]] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def call(self, op: str, args: dict[str, object]) -> dict[str, object]:
        self.calls.append((op, args))
        if op == "nginx.validate_config":
            return {"valid": True}
        return {"reloaded": "fake-rootd"}


@pytest.fixture(autouse=True)
def fake_rootd(monkeypatch) -> type[FakeRootdClient]:
    """Route rootd calls to the fake; the sink answers; port 25 is not probed."""
    FakeRootdClient.calls = []
    for module in _CLIENT_USERS:
        monkeypatch.setattr(module, "LocalRootdClient", FakeRootdClient)
    for module in _RELOAD_USERS:
        monkeypatch.setattr(module, "reload_service", lambda _service: "fake-rootd")
    monkeypatch.setattr(onramp, "check_sink_answers", lambda: None)
    monkeypatch.setattr(
        server_cli,
        "_egress_status",
        lambda: ("unverified", "outbound port 25 not probed in tests"),
    )
    return FakeRootdClient
