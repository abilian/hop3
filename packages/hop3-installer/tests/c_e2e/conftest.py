# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Pytest fixtures for E2E installer tests.

Provides multi-backend support for testing installers on:
- Docker containers (the default target)
- SSH hosts — EXPLICIT opt-in only, via ``--ssh-host HOST`` (root conftest)
- Vagrant VMs (when ``--vagrant`` is used)

CLI options:
    --docker        Run against Docker (this is the default with no flags)
    --ssh-host HOST Run against a remote SSH host (explicit; from root conftest)
    --vagrant       Enable Vagrant backend

Target selection (ADR 043): with NO flags, only Docker runs. Any explicit flag
selects exactly the requested targets. A remote host is NEVER taken from an env
var (HOP3_TEST_HOST / HOP3_DEV_HOST are taboo) — only from ``--ssh-host``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from .utils import bundle_installers, get_backend
from .utils.backends import (
    docker_available,
    set_ssh_host,
    ssh_host_connectable,
    vagrant_installed,
)
from .utils.installers import get_packages_dir

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from .utils.backends import Backend


# =============================================================================
# CLI Options
# =============================================================================


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add installer-specific target flags (``--ssh-host`` is registered at root)."""
    group = parser.getgroup("hop3", "Hop3 test options")
    group.addoption(
        "--docker",
        action="store_true",
        default=False,
        help="Run against Docker (the default target when no flag is given)",
    )
    group.addoption(
        "--vagrant",
        action="store_true",
        default=False,
        help="Enable Vagrant backend (slow, starts VMs)",
    )


# Env vars the `hop3-deploy-server` subprocess reads to pick a target
# (deployer/config.py). Cleared so a bare `hop3-deploy-server` spawned by a test
# can't inherit a real host. The remote-host selectors (HOP3_DEV_HOST /
# HOP3_TEST_HOST / HOP3_TEST_SERVER) are already stripped by the root conftest.
_AMBIENT_DEPLOY_TARGET_VARS = ("HOP3_HOST", "HOP3_DOCKER")


def pytest_configure(config: pytest.Config) -> None:
    """
    Neutralise ambient targeting, then wire the explicit ``--ssh-host``.

    The remote host comes ONLY from ``--ssh-host`` (an explicit flag); it is
    never read from the environment. With no ``--ssh-host``, SSH is disabled and
    tests run against Docker.
    """
    for var in _AMBIENT_DEPLOY_TARGET_VARS:
        os.environ.pop(var, None)
    set_ssh_host(config.getoption("--ssh-host"))


def _explicit_target_requested(config: pytest.Config) -> bool:
    """Whether the user explicitly named any target (Docker / SSH / Vagrant)."""
    return (
        config.getoption("--docker")
        or config.getoption("--ssh-host") is not None
        or config.getoption("--vagrant")
    )


def _select_targets(
    config: pytest.Config,
    *,
    docker_label: str,
    include_vagrant: bool,
    check_ssh_connectable: bool,
) -> list[str]:
    """
    Resolve enabled targets. Docker is the default; SSH is explicit-only.

    - Docker runs unless the user explicitly asked for a *different* target.
    - SSH runs only when ``--ssh-host`` was given (never from an env var).
    - Vagrant runs only with ``--vagrant``.
    """
    explicit = _explicit_target_requested(config)
    targets: list[str] = []

    if (config.getoption("--docker") or not explicit) and docker_available():
        targets.append(docker_label)

    if config.getoption("--ssh-host") is not None and (
        not check_ssh_connectable or ssh_host_connectable()
    ):
        targets.append("ssh")

    if include_vagrant and config.getoption("--vagrant") and vagrant_installed():
        targets.append("vagrant")

    return targets


def get_enabled_backends(config: pytest.Config) -> list[str]:
    """Enabled backends (Docker default; SSH via --ssh-host; Vagrant via flag)."""
    return _select_targets(
        config,
        docker_label="docker",
        include_vagrant=True,
        check_ssh_connectable=False,
    )


def get_enabled_systemd_backends(config: pytest.Config) -> list[str]:
    """Enabled systemd-capable backends (Docker-systemd default; SSH via flag)."""
    return _select_targets(
        config,
        docker_label="docker-systemd",
        include_vagrant=True,
        check_ssh_connectable=False,
    )


def get_enabled_deploy_targets(config: pytest.Config) -> list[str]:
    """Enabled hop3-deploy targets (Docker default; SSH via flag, connectivity-checked)."""
    return _select_targets(
        config,
        docker_label="docker",
        include_vagrant=False,
        check_ssh_connectable=True,
    )


# =============================================================================
# Dynamic Parametrization
# =============================================================================


def _no_target_reason(config: pytest.Config, kind: str) -> str:
    """
    Actionable skip reason when no target is enabled.

    The common case — no ``--ssh-host`` and a down Docker daemon — must say so
    (a bare "no targets available" hid that Docker/OrbStack simply wasn't
    running), not read as "nothing to run".
    """
    if config.getoption("--ssh-host") is None and not docker_available():
        return (
            f"No {kind}: Docker is the default target but the Docker daemon "
            "isn't reachable — start Docker (e.g. `orb start` for OrbStack, or "
            "Docker Desktop). Or pass --ssh-host <host> to test a remote server."
        )
    if config.getoption("--ssh-host") is not None:
        return (
            f"No {kind}: --ssh-host was given but the host isn't reachable "
            "(SSH connect failed); check the host/credentials."
        )
    return f"No {kind}: pass --docker, --ssh-host <host>, or --vagrant."


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Dynamically parametrize fixtures based on CLI options."""
    if "backend" in metafunc.fixturenames:
        backends = get_enabled_backends(metafunc.config)
        if not backends:
            pytest.skip(_no_target_reason(metafunc.config, "backends available"))
        metafunc.parametrize("backend", backends, indirect=True, scope="module")

    if "systemd_backend" in metafunc.fixturenames:
        backends = get_enabled_systemd_backends(metafunc.config)
        if not backends:
            pytest.skip(
                _no_target_reason(metafunc.config, "systemd backends available")
            )
        metafunc.parametrize("systemd_backend", backends, indirect=True, scope="module")

    if "deploy_target" in metafunc.fixturenames:
        targets = get_enabled_deploy_targets(metafunc.config)
        if not targets:
            pytest.skip(_no_target_reason(metafunc.config, "deploy targets available"))
        metafunc.parametrize("deploy_target", targets, scope="module")


# =============================================================================
# Backend Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def backend(request: pytest.FixtureRequest) -> Generator[Backend]:
    """
    Provide a test backend (Docker, SSH, or Vagrant).

    This fixture is dynamically parametrized based on CLI options.
    Tests using this fixture will run once per enabled backend.
    """
    backend_type = request.param
    backend_instance = get_backend(backend_type)

    if not backend_instance.setup():
        pytest.skip(f"Failed to setup {backend_type} backend")

    yield backend_instance

    backend_instance.teardown()


@pytest.fixture(scope="module")
def systemd_backend(request: pytest.FixtureRequest) -> Generator[Backend]:
    """
    Provide a test backend with systemd support.

    This fixture is dynamically parametrized based on CLI options.
    Backends with systemd support:
    - docker-systemd: Docker with systemd image
    - ssh: Remote SSH hosts (typically have systemd)
    - vagrant: Vagrant VMs (have systemd)

    Use this fixture for tests that require systemd (service tests).
    """
    backend_type = request.param
    backend_instance = get_backend(backend_type)

    if not backend_instance.setup():
        pytest.skip(f"Failed to setup {backend_type} backend")

    yield backend_instance

    backend_instance.teardown()


# =============================================================================
# Installer Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def bundled_installers(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Generate bundled installer scripts."""
    out_dir = tmp_path_factory.mktemp("installers")
    return bundle_installers(out_dir)


@pytest.fixture(scope="module")
def hop3_packages_dir() -> Path:
    """Get the path to the hop3 packages directory."""
    packages_dir = get_packages_dir()
    if not packages_dir.exists():
        pytest.fail(f"Packages directory not found: {packages_dir}")
    return packages_dir
