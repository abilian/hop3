# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A Docker deploy must not inherit a host from the environment.

`--docker` names the target: a container, reached on loopback. But the config is
built from the environment first, and `HOP3_HOST` / `HOP3_DEV_HOST` were read
before anyone knew this was a Docker run — so a shell with a dev box exported
sent a `--docker` deploy off to configure the local CLI against that box. The
run printed "CLI configured to connect to http://hop3-dev.abilian.com:8000" two
lines before "Server URL: http://localhost:8000", and the next `hop3` command
would have gone to the remote server.

ADR 043 forbids exactly this for pytest — an ambient variable deciding which
machine a run touches. The reason does not stop at pytest.
"""

from __future__ import annotations

import pytest
from hop3_installer.deployer.cli import _apply_target_overrides
from hop3_installer.deployer.config import DeployConfig

AMBIENT = "hop3-dev.example.com"


class _Args:
    """argparse.Namespace stand-in: any flag not set is absent, i.e. None."""

    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)

    def __getattr__(self, name: str) -> None:
        return None


@pytest.fixture
def ambient_host(monkeypatch):
    monkeypatch.setenv("HOP3_DEV_HOST", AMBIENT)
    monkeypatch.delenv("HOP3_HOST", raising=False)
    monkeypatch.delenv("HOP3_DOCKER", raising=False)


def test_an_ambient_host_still_reaches_a_normal_deploy(ambient_host):
    """The variable is not being disabled — only ignored where it is wrong."""
    assert DeployConfig.from_env().host == AMBIENT


def test_hop3_docker_ignores_the_ambient_host(ambient_host, monkeypatch):
    monkeypatch.setenv("HOP3_DOCKER", "1")

    config = DeployConfig.from_env()

    assert config.use_docker is True
    assert config.host == ""


def test_the_docker_flag_clears_a_host_the_environment_supplied(ambient_host):
    """
    The path `make test-apps` takes: `hop3-deploy-server --docker`.

    `from_env()` runs before the flag is applied, so the host is already there
    when `--docker` arrives — clearing it is the whole fix.
    """
    config = DeployConfig.from_env()
    assert config.host == AMBIENT  # the leak, before the flag lands

    _apply_target_overrides(config, _Args(docker=True, docker_container="test"))

    assert config.use_docker is True
    assert config.host == ""


def test_docker_and_an_explicit_host_are_refused(ambient_host):
    """
    Two targets named at once is a contradiction, not a precedence puzzle.

    Silently letting one win is how a run ends up somewhere nobody chose.
    """
    config = DeployConfig.from_env()

    with pytest.raises(SystemExit, match="cannot be combined"):
        _apply_target_overrides(config, _Args(docker=True, host="someserver"))


def test_docker_and_a_provider_are_refused(ambient_host):
    config = DeployConfig.from_env()

    with pytest.raises(SystemExit, match="cannot be combined"):
        _apply_target_overrides(config, _Args(docker=True, provider="hetzner"))
