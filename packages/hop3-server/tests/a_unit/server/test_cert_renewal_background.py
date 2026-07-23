# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for the CertRenewalService background worker.

Covers the thread lifecycle and the cycle's reload contract (reload nginx only
when something was actually renewed). The renewal decision itself is tested in
test_cert_renewal_service.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from hop3.platform.cert_renewal import RenewOutcome
from hop3.server import cert_renewal_service
from hop3.server.cert_renewal_service import CertRenewalService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session


class _MockSession:
    """A context-manager session; app listing is stubbed via AppRepository."""

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _StubRepo:
    def __init__(self, **_kw):
        pass

    def list_all_ordered(self):
        return []


def _service(**kwargs) -> CertRenewalService:
    return CertRenewalService(cast("Callable[[], Session]", _MockSession), **kwargs)


def test_start_stop():
    # Long delays so no cycle fires during the lifecycle check.
    service = _service(interval=100.0, initial_delay=100.0)
    service.start()
    assert service.is_running()
    service.stop()
    assert not service.is_running()


def test_run_once_reloads_when_renewed(monkeypatch):
    monkeypatch.setattr(
        cert_renewal_service,
        "renew_due_certs",
        lambda _apps, **_kw: RenewOutcome(renewed=["app (a.example.com)"], checked=1),
    )
    monkeypatch.setattr(cert_renewal_service, "AppRepository", _StubRepo)
    reloaded: list[bool] = []
    monkeypatch.setattr(
        cert_renewal_service, "reload_nginx", lambda: reloaded.append(True)
    )

    outcome = _service().run_once()

    assert outcome.renewed == ["app (a.example.com)"]
    assert reloaded == [True]


def test_run_once_no_reload_when_nothing_due(monkeypatch):
    monkeypatch.setattr(
        cert_renewal_service,
        "renew_due_certs",
        lambda _apps, **_kw: RenewOutcome(checked=2),
    )
    monkeypatch.setattr(cert_renewal_service, "AppRepository", _StubRepo)
    reloaded: list[bool] = []
    monkeypatch.setattr(
        cert_renewal_service, "reload_nginx", lambda: reloaded.append(True)
    )

    outcome = _service().run_once()

    assert outcome.renewed == []
    assert reloaded == []
