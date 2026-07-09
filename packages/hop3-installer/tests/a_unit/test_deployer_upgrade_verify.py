# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""A server upgrade must VERIFY the server came back up.

The migration runs forward before the restart, so a restart that starts the
systemd unit but leaves the server crashing must NOT be reported as success —
neither the update paths nor the admin-domain restart (the last one before the
"Deployment complete!" banner). See local-notes/specs/upgrades.md §1.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make the health-poll budget elapse instantly.

    deploy.py does ``import time; time.sleep(delay)``; patch the real ``time``
    module so the default 15x2s poll runs fast. The dotted path targets ``time``
    directly on purpose — ``hop3_installer.deployer.deploy`` re-exports a
    ``deploy`` function that shadows the submodule, so a
    ``hop3_installer.deployer.deploy.time`` path fails to resolve.
    """
    monkeypatch.setattr("time.sleep", lambda *_a: None)


class _Backend:
    """Records commands; the curl health probe reflects ``healthy``."""

    def __init__(self, healthy: bool):
        self.healthy = healthy
        self.commands: list[str] = []

    def run(self, cmd, check=False):
        self.commands.append(cmd)
        ok = "curl" not in cmd or self.healthy
        return SimpleNamespace(
            success=ok, stdout="", stderr="", returncode=0 if ok else 1
        )

    def service_restart_command(self, service):
        return f"systemctl restart {service}"

    def restart_service(self, service):
        return self.run(self.service_restart_command(service))


class _UpdateBackend(_Backend):
    """Adds the outputs the update paths read (git HEAD, pip version)."""

    def run(self, cmd, check=False):
        self.commands.append(cmd)
        stdout = ""
        if "rev-parse HEAD" in cmd:
            stdout = "OLDSHA123"
        elif "pip show hop3-server" in cmd:
            stdout = "Name: hop3-server\nVersion: 0.6.2\n"
        ok = "curl" not in cmd or self.healthy
        return SimpleNamespace(
            success=ok, stdout=stdout, stderr="", returncode=0 if ok else 1
        )


def _deployer(backend, **config):
    return Deployer(DeployConfig(**config), backend=backend)  # type: ignore[arg-type]


def _probes(backend) -> int:
    return sum("curl" in c for c in backend.commands)


# ---- the shared helper ------------------------------------------------------


def test_restart_and_verify_succeeds_when_server_answers():
    backend = _Backend(healthy=True)
    assert _deployer(backend)._restart_and_verify("the upgrade", "revert-hint") is True
    assert any("systemctl restart hop3-server" in c for c in backend.commands)
    assert _probes(backend) == 1  # actually probed, stopped on the answer


def test_restart_and_verify_fails_loud_when_server_stays_down(capsys):
    # The critical no-fake-success case: the restart "worked" (systemd) but the
    # server never answers -> False, and the recovery path is surfaced.
    backend = _Backend(healthy=False)

    result = _deployer(backend)._restart_and_verify(
        "the upgrade", "git reset --hard OLDSHA && ..."
    )

    assert result is False
    out = capsys.readouterr().out
    assert "did NOT come back up" in out
    assert "git reset --hard OLDSHA" in out  # the recovery path is surfaced
    assert "journalctl" in out


def test_wait_until_healthy_gives_up_after_retries():
    backend = _Backend(healthy=False)
    assert _deployer(backend)._wait_until_server_healthy(retries=3, delay=0) is False
    assert _probes(backend) == 3  # polled the full budget


def test_wait_until_healthy_returns_on_first_answer():
    backend = _Backend(healthy=True)
    assert _deployer(backend)._wait_until_server_healthy(retries=5, delay=0) is True
    assert _probes(backend) == 1  # stopped after the first success


# ---- every update path verifies-and-propagates ------------------------------

_PATHS = [
    ("_update_from_git", {"use_git": True}),
    ("_update_from_pypi", {}),
]


@pytest.mark.parametrize(("path", "config"), _PATHS)
def test_update_path_fails_loud_when_server_down(path, config):
    # The headline guarantee: an update path must NOT report success when the
    # new server never answers — each routes through _restart_and_verify.
    backend = _UpdateBackend(healthy=False)
    assert getattr(_deployer(backend, **config), path)() is False
    assert _probes(backend) >= 1  # it actually probed


@pytest.mark.parametrize(("path", "config"), _PATHS)
def test_update_path_succeeds_when_healthy(path, config):
    backend = _UpdateBackend(healthy=True)
    assert getattr(_deployer(backend, **config), path)() is True


# ---- the admin-domain restart (the LAST restart before "complete") ----------


def test_admin_domain_restart_fails_loud_when_server_down():
    # Regression: _persist_admin_domain used to restart fire-and-forget and
    # return True, letting a dead server be reported as "Deployment complete!".
    deployer = _deployer(_Backend(healthy=False))
    assert deployer._persist_admin_domain("admin.example.com") is False


def test_admin_domain_restart_succeeds_when_server_up():
    deployer = _deployer(_Backend(healthy=True))
    assert deployer._persist_admin_domain("admin.example.com") is True
