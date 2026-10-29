# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The deployer reloads nginx through hop3-rootd's verified `nginx.reload` op.

A reload command exiting 0 is not an applied config: nginx signals its master,
and a rejected config (a bind conflict) keeps the old workers serving while
the deploy reports success. rootd's op validates, reloads with the method fit
for the process manager (systemd, or supervisor on the Docker target), and
confirms a fresh worker forked. The deployer calls it from the server venv.
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer


def _result(ok: bool, stderr: str = ""):
    return SimpleNamespace(
        success=ok, stdout="", stderr=stderr, returncode=0 if ok else 1
    )


class _NginxBackend:
    """Records commands with their stdin; the rootd call answers ``ok``."""

    def __init__(self, *, ok: bool, stderr: str = ""):
        self.ok = ok
        self.stderr = stderr
        self.tried: list[tuple[str, str | None]] = []

    def run(self, cmd, check=False, stdin=None):
        self.tried.append((cmd, stdin))
        return _result(self.ok, self.stderr)


def _deployer(backend) -> Deployer:
    return Deployer(DeployConfig(), backend=backend)  # type: ignore[arg-type]


def test_reload_goes_through_rootd_never_a_bare_reload_command():
    backend = _NginxBackend(ok=True)
    assert _deployer(backend)._reload_nginx() is True

    [(cmd, stdin)] = backend.tried
    # As hop3, never root: the interpreter lives in hop3's writable venv.
    assert cmd == "su - hop3 -c '/home/hop3/venv/bin/python3 -'"
    assert stdin is not None
    assert "LocalRootdClient" in stdin
    assert "'nginx.reload'" in stdin
    assert "systemctl" not in cmd
    assert "nginx -s" not in cmd


def test_a_refused_reload_fails_with_rootds_reason(capsys):
    backend = _NginxBackend(ok=False, stderr="no fresh nginx worker after reload")
    assert _deployer(backend)._reload_nginx() is False
    assert "no fresh nginx worker after reload" in capsys.readouterr().out


# --- a failed reload must fail the deploy, not warn-and-continue --------------


class _TlsBackend:
    """
    Everything succeeds except the rootd nginx reload when
    ``reload_ok`` is False. Cert-existence probes report ``cert_present``.
    """

    def __init__(self, *, reload_ok: bool, cert_present: bool = False):
        self.reload_ok = reload_ok
        self.cert_present = cert_present

    def run(self, cmd, check=False, stdin=None):
        if stdin and "nginx.reload" in stdin:
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
