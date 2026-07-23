# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
nginx reload must work on both systemd and supervisor (Docker) targets.

The Docker deploy target runs nginx under supervisor (no systemd), where a plain
`systemctl reload nginx` silently no-ops — leaving the just-written vhost stale
while the deploy reports success. The deployer tries systemctl first, then falls
back to `nginx -s reload` (which signals the master directly), mirroring
hop3-rootd's ops/nginx.py reload chain.
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer


class _NginxBackend:
    """Succeeds only for the reload commands named in ``works``."""

    def __init__(self, works: set[str]):
        self.works = works
        self.tried: list[str] = []

    def run(self, cmd, check=False):
        self.tried.append(cmd)
        return SimpleNamespace(
            success=cmd in self.works, stdout="", stderr="", returncode=0
        )


def _deployer(backend) -> Deployer:
    return Deployer(DeployConfig(), backend=backend)  # type: ignore[arg-type]


def test_systemd_host_uses_systemctl_and_stops():
    backend = _NginxBackend({"systemctl reload nginx"})
    assert _deployer(backend)._reload_nginx() is True
    assert backend.tried == ["systemctl reload nginx"]  # stops on first success


def test_supervisor_host_falls_back_to_nginx_s_reload():
    # No systemd -> systemctl fails -> the `nginx -s reload` fallback works.
    backend = _NginxBackend({"nginx -s reload"})
    assert _deployer(backend)._reload_nginx() is True
    assert backend.tried == ["systemctl reload nginx", "nginx -s reload"]


def test_reports_failure_when_no_method_works():
    backend = _NginxBackend(set())
    assert _deployer(backend)._reload_nginx() is False
    assert backend.tried == ["systemctl reload nginx", "nginx -s reload"]


# --- a failed reload must fail the deploy, not warn-and-continue --------------


class _TlsBackend:
    """
    Everything succeeds except the two nginx reload commands when
    ``reload_ok`` is False. Cert-existence probes report ``cert_present``.
    """

    def __init__(self, *, reload_ok: bool, cert_present: bool = False):
        self.reload_ok = reload_ok
        self.cert_present = cert_present

    def run(self, cmd, check=False):
        if "reload nginx" in cmd or "nginx -s reload" in cmd:
            ok = self.reload_ok
        elif cmd.startswith(("test -f", "test -s")):
            ok = self.cert_present
        else:
            ok = True  # writes, `nginx -t`, openssl, chmod/chown, ...
        return SimpleNamespace(success=ok, stdout="", stderr="", returncode=0)


def test_admin_nginx_fails_loud_when_reload_fails():
    # Config writes + `nginx -t` pass, but nginx won't reload -> the admin vhost
    # isn't live, so the step must fail (its caller aborts the deploy).
    assert (
        _deployer(_TlsBackend(reload_ok=False))._setup_admin_nginx("x.example") is False
    )
    assert (
        _deployer(_TlsBackend(reload_ok=True))._setup_admin_nginx("x.example") is True
    )


def test_ssl_setup_fails_loud_when_reload_fails():
    # Self-signed path (no --acme-email): cert is generated, but the HTTPS vhost
    # can't be reloaded -> _setup_admin_ssl must report failure, not swallow it.
    assert (
        _deployer(_TlsBackend(reload_ok=False))._setup_admin_ssl("x.example") is False
    )
    assert _deployer(_TlsBackend(reload_ok=True))._setup_admin_ssl("x.example") is True
