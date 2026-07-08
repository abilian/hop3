# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the `hop3-test upgrade-chain` command's config + guards.

The deploy/assert loop needs a fresh box + real deploys (covered by the e2e run);
here we pin the pure logic: a hop config runs the right (checkout's own) deployer,
`local` resolves to the repo, and the command refuses wrong invocations.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from hop3_testing.cli.commands.upgrade_chain import (
    _checkout,
    _hop_config,
    upgrade_chain,
)


def test_hop_config_runs_the_checkouts_own_deployer():
    # Each hop deploys via `uv run` from its checkout, with stable --local flags.
    cfg = _hop_config(cwd=Path("/tmp/wt"), clean=True, verbose=False)
    assert cfg.source == "local"
    assert cfg.legacy_flags is True  # emits --local, accepted by every version
    assert cfg.command_prefix == ["uv", "run"]
    assert cfg.cwd == Path("/tmp/wt")


def test_checkout_local_is_the_repo_root():
    repo = Path("/repo")
    worktrees: list[Path] = []
    # `local` must not create a worktree — it's the current tree.
    assert _checkout("local", repo, Path("/tmp"), worktrees) == repo
    assert worktrees == []


def _invoke(*args):
    return CliRunner().invoke(upgrade_chain, list(args), obj={})


def test_requires_at_least_two_hops():
    result = _invoke("--docker", "--chain", "0.6.2")
    assert result.exit_code != 0
    assert "two hops" in result.output


def test_requires_a_target():
    result = _invoke("--chain", "0.6.2,local")
    assert result.exit_code != 0
    assert "target" in result.output.lower()


def test_docker_invocation_reaches_deploy_loop(monkeypatch):
    # A valid --docker invocation gets past parsing/checkout and starts deploying
    # (stubbed to fail fast, so no real Docker/worktrees are touched).
    class _Boom:
        def __init__(self, *args, **kwargs): ...
        def start(self):
            raise RuntimeError  # a failed deploy -> loud summary + exit 1

        def stop(self): ...

    monkeypatch.setattr("hop3_testing.cli.commands.upgrade_chain.DockerTarget", _Boom)
    # `local,local` avoids any git worktree checkout in this unit test.
    result = _invoke("--docker", "--chain", "local,local")
    assert result.exit_code == 1
    assert "FAILED" in result.output
