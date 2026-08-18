# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The update path must not restart through a process manager that isn't there.

`_start_docker_services` runs *after* install-or-update. That order is fine for a
fresh install — install, then start supervisor — but the update branch restarts
hop3-server via supervisor before anything has ensured supervisor exists.

A deploy that dies between installing and starting services leaves a box that
answers `is_hop3_installed()` with yes and has no supervisor at all. That is what
an installer exiting non-zero on a verification warning did: the container had
hop3-server, postgres and mysql all installed and running, and an empty
`/etc/supervisor/conf.d`. Every later run then took the update branch and failed
identically —

    ✗ Server did NOT come back up after the upgrade.
    ✗   The restart command failed: supervisorctl restart hop3-server
        unix:///var/run/supervisor.sock no such file

— with no way out but `--clean`. Three consecutive runs failed that way before
the cause was visible, which is the shape CLAUDE.md calls order-dependent: the
outcome of a run decided by what ran before it.

`start_services()` is idempotent (reread+update when supervisord is already
running) and a no-op on systemd targets, so ensuring it here costs nothing in the
normal case and un-sticks the broken one.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_installer.common import ServiceStartError
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer


class _Backend:
    """An installed box. Records the order of the calls that matter."""

    def __init__(self, *, start_raises: bool = False) -> None:
        self.calls: list[str] = []
        self.start_raises = start_raises

    def is_hop3_installed(self) -> bool:
        return True

    def start_services(self) -> None:
        self.calls.append("start_services")
        if self.start_raises:
            msg = "supervisord would not start"
            raise ServiceStartError(msg)


def _config() -> DeployConfig:
    """
    A Docker deploy with no extra features.

    `DeployConfig` defaults `with_features` to `["docker"]`, which adds a step
    after the update. This suite is about what happens *before* the update.
    """
    config = DeployConfig(use_docker=True)
    config.with_features = []
    return config


@pytest.fixture
def deployer_and_backend():
    backend = _Backend()
    deployer = Deployer(_config(), backend=backend)  # type: ignore[arg-type]
    return deployer, backend


def test_services_are_ensured_before_the_update_restarts_anything(
    deployer_and_backend,
):
    deployer, backend = deployer_and_backend

    with patch.object(
        deployer, "_update", side_effect=lambda: backend.calls.append("update") or True
    ):
        success, _ = deployer._handle_install_or_update(0, None)

    assert success is True
    assert backend.calls == ["start_services", "update"]


def test_a_process_manager_that_will_not_start_fails_the_deploy():
    """Not a warning: every later step restarts through it."""
    backend = _Backend(start_raises=True)
    deployer = Deployer(_config(), backend=backend)  # type: ignore[arg-type]

    with patch.object(deployer, "_update") as update:
        success, _ = deployer._handle_install_or_update(0, None)

    assert success is False
    update.assert_not_called()


def test_a_fresh_install_does_not_take_this_path():
    """`start_services` still runs after `_install`, in its own step."""
    backend = _Backend()
    backend.is_hop3_installed = lambda: False  # type: ignore[method-assign]
    deployer = Deployer(_config(), backend=backend)  # type: ignore[arg-type]

    with patch.object(deployer, "_install", return_value=True):
        success, _ = deployer._handle_install_or_update(0, None)

    assert success is True
    assert backend.calls == []
