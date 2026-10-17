# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A failed image build stops a Docker deploy.

It fell back to a bare ``ubuntu:24.04`` with a few apt packages, so the run
went on against a machine the e2e image does not describe, and said so in one
printed line.
"""

from __future__ import annotations

import pytest
from hop3_installer.deployer.backends.docker import DockerDeployBackend
from hop3_installer.deployer.config import DeployConfig


@pytest.fixture(autouse=True)
def _local_daemon(monkeypatch):
    """setup() resolves the daemon; never ask a real `docker` from a unit test."""
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")


def test_a_failed_build_starts_no_container():
    backend = DockerDeployBackend(DeployConfig(use_docker=True, clean_before=True))
    started: list[str] = []
    backend._docker_unavailable_reason = lambda: None
    backend._container_running = lambda: False
    backend._reclaim_orphans = list
    backend._remove_container = lambda: None
    backend._build_image = lambda: False
    backend._start_container = lambda: (started.append(backend.image), True)[1]

    assert backend.setup() is False
    assert started == []
