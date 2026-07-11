# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Engine CLI contract consumed by hop3-testlab (ADR 052 safety net, Phase 0).

The Test Lab (`hop3_testlab/worker.py`) shells out to `hop3-test run` with a
fixed set of flags. Renaming/removing any of them (planned by ADR 052) silently
breaks the nightly unless done in lockstep with the Lab. These tests pin the
current CLI surface so a break shows up here in `make test`, not at 3am.

When ADR 052 renames these (e.g. `system`→`run`, `--ssh`+`--host`→`--host`,
`--ssh-key`→`--identity`, `--deploy-from`→`--from`), update BOTH this contract
and `worker.py` in the same change — and keep the old spellings as accepted
aliases until the Lab is migrated.
"""

from __future__ import annotations

import click
from click.testing import CliRunner
from hop3_testing.cli import cli
from hop3_testing.cli.commands import (
    list_tests,
    register_commands,
    system_test,
    test as testmod,
    why_cmd,
)


def _flags(command: click.Command) -> set[str]:
    """All option strings the command accepts (e.g. '--host', '-x')."""
    return {opt for param in command.params for opt in param.opts}


def test_registered_subcommands_present():
    group = click.Group("hop3-test")
    register_commands(group)
    # `run` is canonical; `system` stays a deprecated alias. The image sweep
    # folded into `run --images` (ADR 052 D9) — no separate matrix/cloud command.
    for name in ("run", "system", "list", "why", "upgrade-chain"):
        assert name in group.commands, f"hop3-test lost the '{name}' subcommand"
    for gone in ("matrix", "cloud"):
        assert gone not in group.commands, f"'{gone}' should be folded into run"
    # Silence unused-import linters — these are the command objects under test.
    assert {system_test.name, list_tests.name, why_cmd.name} == {"run", "list", "why"}


def test_system_is_an_alias_of_run():
    group = click.Group("hop3-test")
    register_commands(group)
    assert group.commands["system"] is group.commands["run"]  # same command object


def test_run_provides_the_image_sweep_surface():
    # The former `matrix` flags now live on `run` (ADR 052 D9).
    for flag in ("--images", "--list-images", "--provider", "--image"):
        assert flag in _flags(system_test), f"`run` lost {flag} after the matrix fold"


def test_system_accepts_the_flags_the_testlab_passes():
    # Every flag hop3_testlab/worker.py puts on the argv.
    required = {
        "--docker",
        "--ssh",
        "--host",
        "--identity",  # ADR 052 D2 canonical SSH key flag
        "--ssh-key",  # back-compat alias (same option)
        "--with",
        "--mode",
        "--report",
        "--from",  # ADR 052 D3 canonical source selector
        "--deploy-from",  # back-compat alias (same option)
        "--branch",
    }
    missing = required - _flags(system_test)
    assert not missing, f"`hop3-test run` no longer accepts: {sorted(missing)}"


def test_system_docker_argv_parses():
    # The Lab's docker invocation must parse without error (arity/choices intact).
    ctx = system_test.make_context(
        "run",
        ["--docker", "--with", "all", "--mode", "smoke", "--report", "html"],
    )
    assert ctx.params["target_type"] == "docker"


def test_system_ssh_argv_parses():
    ctx = system_test.make_context(
        "run",
        [
            "--ssh",
            "--host",
            "h.example",
            "--ssh-key",
            "/k",
            "--with",
            "all",
            "--deploy-from",
            "git",
            "--branch",
            "main",
            "--report",
            "html",
        ],
    )
    assert ctx.params["target_type"] == "remote"
    assert ctx.params["host"] == "h.example"


def test_from_and_deploy_from_are_the_same_option():
    # ADR 052 D3: --from is canonical; --deploy-from stays as an accepted alias.
    for flag in ("--from", "--deploy-from"):
        ctx = system_test.make_context("run", ["--docker", flag, "git"])
        assert ctx.params["deploy_from"] == "git"


def test_host_alone_selects_remote(monkeypatch):
    # ADR 052 D2: --host implies the remote target — the Lab now passes --host
    # WITHOUT --ssh. Short-circuit test resolution so we assert target selection
    # without deploying.
    monkeypatch.setattr(testmod, "_resolve_tests", lambda *a, **k: [])
    monkeypatch.delenv("HOP3_TEST_HOST", raising=False)
    result = CliRunner().invoke(cli, ["run", "--host", "1.2.3.4"])
    # Remote was selected: no "specify --docker/--host" error, and it reaches the
    # "No tests found" early return (exit 0).
    assert result.exit_code == 0
    assert "No tests found" in result.output
    assert "specify --docker" not in (result.stderr or "")


def test_no_target_and_no_host_errors(monkeypatch):
    # --host resolves from $HOP3_HOST (ADR 052); clear it so a leaked value can't
    # select a target. (HOP3_TEST_HOST is retired and no longer consulted.)
    monkeypatch.delenv("HOP3_HOST", raising=False)
    result = CliRunner().invoke(cli, ["run"])
    assert result.exit_code != 0
    assert "specify --docker" in result.stderr
