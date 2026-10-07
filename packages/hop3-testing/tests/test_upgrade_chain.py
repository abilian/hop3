# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for the `hop3-test upgrade-chain` command's config + guards.

The deploy/assert loop needs a fresh box + real deploys (covered by the e2e run);
here we pin the pure logic: a hop config runs the right (checkout's own) deployer,
`local` resolves to the repo, and the command refuses wrong invocations.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from hop3_testing.cli.commands.upgrade_chain import (
    _PYTHON,
    _assert_hop,
    _checkout,
    _deployer_script,
    _hop_config,
    upgrade_chain,
)


def test_hop_config_runs_the_checkouts_own_deployer():
    # Each hop deploys via `uv run` from its checkout, with stable --local flags.
    cfg = _hop_config(
        cwd=Path("/tmp/wt"), script="hop3-deploy", clean=True, verbose=False
    )
    assert cfg.source == "local"
    assert cfg.legacy_flags is True  # emits --local, accepted by every version
    # Pinned interpreter: a tag's worktree has no .python-version of its own.
    assert cfg.command_prefix == ["uv", "run", "--python", _PYTHON]
    assert cfg.cwd == Path("/tmp/wt")
    assert cfg.deployer_command == "hop3-deploy"


def _checkout_with_scripts(tmp_path: Path, scripts: str) -> Path:
    installer = tmp_path / "packages" / "hop3-installer"
    installer.mkdir(parents=True)
    (installer / "pyproject.toml").write_text(
        f"[project]\nname='x'\n[project.scripts]\n{scripts}\n"
    )
    return tmp_path


def test_deployer_script_is_read_from_the_checkout(tmp_path):
    # 0.6.x shipped `hop3-deploy`; 0.7+ ships `hop3-deploy-server` plus a
    # deprecated `hop3-deploy` alias. The main entry point is the one to run.
    old = _checkout_with_scripts(
        tmp_path / "old", 'hop3-deploy = "hop3_installer.deployer:main"'
    )
    new = _checkout_with_scripts(
        tmp_path / "new",
        'hop3-deploy-server = "hop3_installer.deployer:main"\n'
        'hop3-deploy = "hop3_installer.deployer:deprecated_main"',
    )
    assert _deployer_script(old) == "hop3-deploy"
    assert _deployer_script(new) == "hop3-deploy-server"


def test_deployer_script_fails_loud_when_absent(tmp_path):
    bare = _checkout_with_scripts(tmp_path, 'hop3-install = "hop3_installer.main:main"')
    with pytest.raises(RuntimeError, match=r"hop3_installer\.deployer:main"):
        _deployer_script(bare)


class _Box:
    """A target whose venv reports a fixed hop3-server version."""

    def __init__(self, version: str) -> None:
        self.version = version

    def exec_run(self, command: str):
        if "hop3_server" in command:
            return 0, self.version + "\n", ""
        if "hop3_rootd" in command:
            return 0, self.version + "\n", ""
        return 0, "c9e4a1b7d2f3 (head)\n", ""


def test_assert_hop_refuses_a_version_the_hop_did_not_install():
    # A fresh 0.6.2 hop once ended with 0.7.3 on the box (the wrong deployer
    # ran via PATH) and the chain passed. The version is now asserted.
    with pytest.raises(RuntimeError, match=r"expected 0\.6\.2"):
        _assert_hop(_Box("0.7.3"), "0.6.2", "0.6.2")
    result = _assert_hop(_Box("0.6.2"), "0.6.2", "0.6.2")
    assert result["version"] == "0.6.2"


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

    # Patch the module object, not a dotted string: `commands/__init__.py` does
    # `from .upgrade_chain import upgrade_chain`, so the string path
    # `…commands.upgrade_chain` resolves to the command, shadowing the submodule.
    module = importlib.import_module("hop3_testing.cli.commands.upgrade_chain")
    monkeypatch.setattr(module, "DockerTarget", _Boom)
    # Syncing the checkout's env is a real `uv sync`; not in a unit test.
    monkeypatch.setattr(module, "_sync_checkout", lambda *_a, **_k: None)
    # `local,local` avoids any git worktree checkout in this unit test.
    result = _invoke("--docker", "--chain", "local,local")
    assert result.exit_code == 1
    assert "FAILED" in result.output


def test_a_seed_with_the_wrong_rights_stops_the_chain(monkeypatch, tmp_path):
    """
    Recorded as found, a failed probe on hop 1 (no token, so all three
    False) compared equal on every later hop: the role migration "passed"
    without being exercised.
    """
    chain = importlib.import_module("hop3_testing.cli.commands.upgrade_chain")
    session = type("S", (), {"deploy": lambda self: None})()
    monkeypatch.setattr(chain, "DeploymentSession", lambda *_a, **_kw: session)
    monkeypatch.setattr(chain, "_hop3", lambda *_a, **_kw: None)
    no_token = chain._Rights(token=False, read_env=False, list_users=False)
    monkeypatch.setattr(chain, "_state", lambda *_a: no_token)
    target = type("T", (), {"cli_env": lambda self: {}})()

    with pytest.raises(RuntimeError, match="wrong baseline"):
        chain._seed(target, tmp_path, "v0.6.2")


def test_a_teardown_that_leaves_something_fails_the_chain(capsys):
    """It printed a ⚠ line and exited 0; on --host, the leftover stays."""
    chain = importlib.import_module("hop3_testing.cli.commands.upgrade_chain")
    ctx = click.Context(click.Command("upgrade-chain"))

    with pytest.raises(click.exceptions.Exit) as exited:
        chain._finish(ctx, ["v0.6.2", "HEAD"], ["could not remove chain-account: x"])

    assert exited.value.exit_code == 1
    assert "could not remove chain-account" in capsys.readouterr().err
