# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Fold single-cloud into `run` (ADR 052 Phase 7b.7).

`hop3-test run --provider hetzner` rebuilds a fresh box (provision_server) then
deploys+tests it via the normal remote path; `matrix` is `run x N images`. These
pin the WIRING (make test). The actual OS rebuild needs a Hetzner cloud smoke.
"""

from __future__ import annotations

from types import SimpleNamespace

import hop3_testing.cli.commands.test as testmod
import hop3_testing.system_tests.multi_distro as md
import pytest
from click.testing import CliRunner
from hop3_testing.cli import cli
from hop3_testing.exceptions import ConfigurationError
from hop3_testing.system_tests.provision import provision_server
from rich.console import Console


def _fake_test():
    # A resolved test needs .name (plan display) + .requirements.services (addon
    # auto-provisioning).
    return SimpleNamespace(name="t", requirements=SimpleNamespace(services=[]))


# --- provision_server pre-flight (fail loud, no cloud) ---------------------


def test_provision_rejects_unknown_provider():
    with pytest.raises(ConfigurationError):
        provision_server(provider="aws")


def test_provision_requires_api_token(monkeypatch):
    monkeypatch.delenv("HETZNER_API_TOKEN", raising=False)
    with pytest.raises(ConfigurationError, match="HETZNER_API_TOKEN"):
        provision_server(provider="hetzner", server_id=123)


def test_provision_requires_server_id(monkeypatch):
    monkeypatch.setenv("HETZNER_API_TOKEN", "tok")
    monkeypatch.delenv("HETZNER_SERVER_ID", raising=False)
    with pytest.raises(ConfigurationError, match="server-id"):
        provision_server(provider="hetzner", server_id=None)


# --- run --provider wiring: provisions, then targets the new IP ------------


def test_run_provider_provisions_then_targets_the_new_ip(monkeypatch):
    monkeypatch.setattr(
        "hop3_testing.system_tests.provision.provision_server",
        lambda **_kw: "203.0.113.99",
    )
    monkeypatch.setattr(testmod, "_resolve_tests", lambda *a, **k: [_fake_test()])

    captured: dict = {}

    class _FakeRemoteTarget:
        def __init__(self, config, deployment=None):
            captured["config"] = config
            captured["deployment"] = deployment

    monkeypatch.setattr(testmod, "RemoteTarget", _FakeRemoteTarget)
    monkeypatch.setattr(testmod, "run_tests", lambda *a, **k: None)
    monkeypatch.delenv("HOP3_TEST_HOST", raising=False)

    result = CliRunner().invoke(
        cli, ["run", "--provider", "hetzner", "--server-id", "123"]
    )
    assert result.exit_code == 0, result.output
    # The remote target points at the freshly rebuilt server's IP.
    assert captured["config"].host == "203.0.113.99"


# --- matrix sweep wiring ---------------------------------------------------


def test_matrix_single_image_is_a_sweep_of_one(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "hop3_testing.system_tests.multi_distro.run_multi_distro_tests",
        lambda **kw: captured.update(kw) or [],
    )
    result = CliRunner().invoke(cli, ["matrix", "--image", "debian-13"])
    assert result.exit_code == 0, result.output
    assert captured["images"] == ["debian-13"]


def test_sweep_leg_invokes_run_provider_via_module(monkeypatch):
    captured: dict = {}

    def _fake_run(cmd, **_kw):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(md.subprocess, "run", _fake_run)
    md.run_test_for_image(
        "ubuntu-24.04",
        Console(),
        app_names=("apps/test-apps-procfile",),
        source="local",
        verbose=True,
    )
    cmd = captured["cmd"]
    # python -m hop3_testing.cli (PATH-independent), -v BEFORE the run subcommand
    assert "hop3_testing.cli" in cmd
    assert cmd.index("-v") < cmd.index("run")
    assert cmd[cmd.index("--provider") + 1] == "hetzner"
    assert cmd[cmd.index("--image") + 1] == "ubuntu-24.04"
    assert cmd[cmd.index("--from") + 1] == "local"
    # app names are `run`'s positional args, mirroring the `run` lexicon
    assert "apps/test-apps-procfile" in cmd


def test_matrix_shares_run_lexicon(monkeypatch):
    """matrix accepts the same deploy lexicon as run: positional apps, --from,
    repeatable --with — and threads them into the sweep (ADR 052 D1)."""
    captured: dict = {}
    monkeypatch.setattr(
        "hop3_testing.system_tests.multi_distro.run_multi_distro_tests",
        lambda **kw: captured.update(kw) or [],
    )
    result = CliRunner().invoke(
        cli,
        [
            "matrix",
            "--image",
            "debian-13",
            "--from",
            "pypi",
            "--with",
            "nix,redis",
            "--with",
            "s3",
            "apps/test-apps-procfile",
            "demos",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["app_names"] == ("apps/test-apps-procfile", "demos")
    assert captured["source"] == "pypi"
    # --with is repeatable AND comma-split, expanded to one --with per feature.
    assert captured["extra_args"] == [
        "--with",
        "nix",
        "--with",
        "redis",
        "--with",
        "s3",
    ]


def test_matrix_use_local_repo_alias_maps_to_from(monkeypatch):
    """The old boolean --no-local-repo folds onto --from pypi (ADR 052 D7)."""
    captured: dict = {}
    monkeypatch.setattr(
        "hop3_testing.system_tests.multi_distro.run_multi_distro_tests",
        lambda **kw: captured.update(kw) or [],
    )
    result = CliRunner().invoke(cli, ["matrix", "--no-local-repo"])
    assert result.exit_code == 0, result.output
    assert captured["source"] == "pypi"
    assert "deprecated" in result.stderr.lower()
