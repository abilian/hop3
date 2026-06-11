# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""The shared cert-renewal service (used by `hop3 cert renew` and the timer).

Locks down domain derivation and the batch contract: only due certs are
reinstalled, a per-app failure is collected (not raised) so the rest still run,
and apps with no real domain are skipped.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.platform import cert_renewal, certificates
from hop3.platform.cert_renewal import app_cert_domain, renew_due_certs


@pytest.fixture
def key_store(tmp_path, monkeypatch):
    """Point the cert store at a throwaway dir (renewal only touches managed certs)."""
    monkeypatch.setattr(certificates, "KEY_STORE", tmp_path)
    return tmp_path


def _manage(store, *domains: str) -> None:
    """Mark domains as hop3-managed by placing a cert file in the store."""
    for domain in domains:
        (store / f"{domain}.crt").write_text("CERT")


def _app(name: str, host_name: str | None = None):
    env_vars = []
    if host_name is not None:
        env_vars = [SimpleNamespace(name="HOST_NAME", value=host_name)]
    return SimpleNamespace(name=name, env_vars=env_vars)


class _Manager:
    """Stub CertificatesManager: per-domain renew returns True/False or raises."""

    def __init__(self, behavior: dict):
        self.behavior = behavior
        self.calls: list[tuple] = []

    def renew(self, domain, *, threshold_days, force):
        self.calls.append((domain, threshold_days, force))
        result = self.behavior[domain]
        if isinstance(result, Exception):
            raise result
        return result


def test_app_cert_domain():
    assert app_cert_domain(_app("a", "edrix.eu")) == "edrix.eu"
    # First host of a multi-host HOST_NAME.
    assert app_cert_domain(_app("a", "edrix.eu www.edrix.eu")) == "edrix.eu"
    # Catch-all and unset => no managed domain.
    assert app_cert_domain(_app("a", "_")) is None
    assert app_cert_domain(_app("a")) is None


def test_renew_due_certs_batch(key_store, monkeypatch):
    _manage(key_store, "ok.example.com", "valid.example.com", "broken.example.com")
    installed: list[tuple] = []
    monkeypatch.setattr(
        cert_renewal,
        "install_cert_to_nginx",
        lambda app, domain: installed.append((app, domain)),
    )
    monkeypatch.setattr(cert_renewal, "verify_cert", lambda _domain: None)
    apps = [
        _app("ok", "ok.example.com"),  # due -> renewed + reinstalled
        _app("valid", "valid.example.com"),  # not due -> left alone
        _app("broken", "broken.example.com"),  # raises -> recorded, not fatal
        _app("nohost"),  # no domain -> skipped, not counted
    ]
    manager = _Manager({
        "ok.example.com": True,
        "valid.example.com": False,
        "broken.example.com": RuntimeError("port 80 unreachable"),
    })

    outcome = renew_due_certs(apps, threshold_days=30, manager=manager)

    assert outcome.checked == 3  # nohost skipped
    assert outcome.renewed == ["ok (ok.example.com)"]
    assert outcome.failed == [("broken (broken.example.com)", "port 80 unreachable")]
    assert installed == [("ok", "ok.example.com")]  # only the renewed one reinstalled


def test_renew_due_certs_passes_force_and_threshold(key_store, monkeypatch):
    _manage(key_store, "x.example.com")
    monkeypatch.setattr(cert_renewal, "install_cert_to_nginx", lambda *a: None)
    monkeypatch.setattr(cert_renewal, "verify_cert", lambda _domain: None)
    manager = _Manager({"x.example.com": True})

    renew_due_certs(
        [_app("x", "x.example.com")], threshold_days=45, force=True, manager=manager
    )

    assert manager.calls == [("x.example.com", 45, True)]


def test_renew_skips_unmanaged_domains(key_store, monkeypatch):
    # No cert on disk -> hop3 doesn't manage it (e.g. the proxy does auto-HTTPS);
    # renewal must not spuriously issue one.
    monkeypatch.setattr(cert_renewal, "install_cert_to_nginx", lambda *a: None)
    monkeypatch.setattr(cert_renewal, "verify_cert", lambda _domain: None)
    manager = _Manager({})  # renew must never be called

    outcome = renew_due_certs([_app("auto", "auto.example.com")], manager=manager)

    assert outcome.checked == 0
    assert outcome.renewed == []
    assert manager.calls == []
