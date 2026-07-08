# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The Docker deploy backend must reuse a running container unless --clean.

Recreating the container on every `hop3-deploy-server --docker` wipes
/home/hop3 (the DB + installed venv), so a second deploy could only ever be a
fresh install — the in-place UPDATE path (upgrades) was unreachable. Honour
--clean instead: reuse when a container is running and --clean is absent.
"""

from __future__ import annotations

from hop3_installer.deployer.backends.docker import DockerDeployBackend
from hop3_installer.deployer.config import DeployConfig


def _backend(*, clean: bool, running: bool):
    """A backend with its container primitives stubbed; records remove/start."""
    backend = DockerDeployBackend(DeployConfig(use_docker=True, clean_before=clean))
    calls: list[str] = []
    backend._docker_available = lambda: True
    backend._container_running = lambda: running
    backend._check_ports_available = list
    backend._build_image = lambda: True
    backend._wait_for_container_ready = lambda: True
    backend._remove_container = lambda: calls.append("remove")
    backend._start_container = lambda: (calls.append("start"), True)[1]
    return backend, calls


def test_reuses_running_container_when_not_clean():
    backend, calls = _backend(clean=False, running=True)
    assert backend.setup() is True
    assert calls == []  # neither removed nor restarted -> reused (upgrade path)


def test_recreates_when_clean():
    backend, calls = _backend(clean=True, running=True)
    assert backend.setup() is True
    assert calls == ["remove", "start"]  # --clean forces a fresh container


def test_recreates_when_no_container_running():
    backend, calls = _backend(clean=False, running=False)
    assert backend.setup() is True
    assert calls == ["remove", "start"]  # nothing to reuse -> fresh


def test_reuse_takes_precedence_over_port_conflict_check():
    # A reused container legitimately holds the ports; the port check (which
    # would flag them) must be skipped when reusing.
    backend, _calls = _backend(clean=False, running=True)
    backend._check_ports_available = lambda: [(8000, "hop3-dev", "Hop3 API")]
    assert backend.setup() is True
