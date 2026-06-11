# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the DomainHealthService background worker."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from hop3.platform.domain_health import DomainHealth
from hop3.server import domain_health_service
from hop3.server.domain_health_service import DomainHealthService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session


class _MockSession:
    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _app(name: str, host: str):
    return SimpleNamespace(
        name=name, env_vars=[SimpleNamespace(name="HOST_NAME", value=host)]
    )


class _StubRepo:
    def __init__(self, **_kw):
        pass

    def list_all_ordered(self):
        return [_app("a", "a.example.com"), _app("catchall", "_")]


def _service(**kwargs) -> DomainHealthService:
    return DomainHealthService(cast("Callable[[], Session]", _MockSession), **kwargs)


def test_start_stop():
    service = _service(interval=100.0, initial_delay=100.0)
    service.start()
    assert service.is_running()
    service.stop()
    assert not service.is_running()


def test_run_once_probes_each_domain_and_stores(monkeypatch):
    monkeypatch.setattr(domain_health_service, "AppRepository", _StubRepo)
    monkeypatch.setattr(
        domain_health_service, "server_ips", lambda: frozenset({"203.0.113.5"})
    )
    monkeypatch.setattr(
        domain_health_service,
        "check_domain",
        lambda domain, **_kw: DomainHealth(domain=domain),
    )
    stored: dict = {}
    monkeypatch.setattr(domain_health_service, "set_domain_health", stored.update)

    out = _service().run_once()

    # Catch-all "_" is skipped; the real domain is probed and stored.
    assert set(out) == {"a.example.com"}
    assert set(stored) == {"a.example.com"}
