# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
`hop3-deploy-server --provider` rebuilds a pristine server before deploying.

Deploying onto a box that already ran Hop3 is how a "fresh install" quietly
becomes an upgrade over someone else's leftovers. `hop3-test run --provider`
already solved this; the deploy CLI needed the same option, spelled the same
way, rather than a second vocabulary for the same idea.
"""

from __future__ import annotations

import argparse
import builtins

import pytest
from hop3_installer.deployer import cli as deploy_cli
from hop3_installer.deployer.config import DeployConfig


def _args(**overrides) -> argparse.Namespace:
    defaults = {
        "host": None,
        "provider": None,
        "image": None,
        "server_id": None,
        "docker": False,
        "docker_image": None,
        "docker_container": None,
        "ssh_user": None,
        "ssh_key": None,
        "verbose": False,
    }
    return argparse.Namespace(**{**defaults, **overrides})


def test_the_parser_accepts_the_same_words_as_hop3_test() -> None:
    """One vocabulary: --provider / --image / --server-id, as in `hop3-test run`."""
    parser = deploy_cli.create_parser()

    parsed = parser.parse_args([
        "--provider",
        "hetzner",
        "--image",
        "ubuntu-24.04",
        "--server-id",
        "42",
    ])

    assert parsed.provider == "hetzner"
    assert parsed.image == "ubuntu-24.04"
    assert parsed.server_id == 42


def test_the_rebuilt_servers_address_becomes_the_target(monkeypatch) -> None:
    """--provider supplies the host; it is not a companion to --host."""
    calls: list[dict] = []

    def _provision(**kwargs):
        calls.append(kwargs)
        return "203.0.113.7"

    monkeypatch.setattr(
        deploy_cli,
        "_provision_pristine_server",
        lambda a: _provision(provider=a.provider, server_id=a.server_id, image=a.image),
    )
    config = DeployConfig()

    deploy_cli._apply_target_overrides(
        config, _args(provider="hetzner", image="ubuntu-24.04", server_id=42)
    )

    assert config.host == "203.0.113.7"
    assert calls == [{"provider": "hetzner", "image": "ubuntu-24.04", "server_id": 42}]


def test_without_provider_the_host_is_used_unchanged() -> None:
    config = DeployConfig()

    deploy_cli._apply_target_overrides(config, _args(host="server.example.com"))

    assert config.host == "server.example.com"


def test_missing_provisioning_support_fails_loudly(monkeypatch) -> None:
    """
    It must not fall back to deploying at whatever --host was set.

    Silently deploying to the old server is the exact opposite of what
    --provider asks for, and the difference is invisible until much later.
    """
    real_import = builtins.__import__

    def _no_hop3_testing(name, *a, **kw):
        if name.startswith("hop3_testing"):
            msg = "no hop3_testing"
            raise ImportError(msg)
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _no_hop3_testing)

    with pytest.raises(SystemExit, match="hop3-testing"):
        deploy_cli._provision_pristine_server(_args(provider="hetzner"))
