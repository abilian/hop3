# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Engine CLI contract consumed by hop3-testlab (ADR 052 safety net, Phase 0).

The Test Lab (`hop3_testlab/worker.py`) shells out to `hop3-test system` with a
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
from hop3_testing.cli.commands import (
    cloud_test,
    list_tests,
    register_commands,
    system_test,
    why_cmd,
)


def _flags(command: click.Command) -> set[str]:
    """All option strings the command accepts (e.g. '--host', '-x')."""
    return {opt for param in command.params for opt in param.opts}


def test_registered_subcommands_present():
    group = click.Group("hop3-test")
    register_commands(group)
    for name in ("system", "list", "cloud", "why"):
        assert name in group.commands, f"hop3-test lost the '{name}' subcommand"
    # Silence unused-import linters — these are the command objects under test.
    assert {system_test.name, cloud_test.name, list_tests.name, why_cmd.name} == {
        "system",
        "cloud",
        "list",
        "why",
    }


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
    assert not missing, f"`hop3-test system` no longer accepts: {sorted(missing)}"


def test_system_docker_argv_parses():
    # The Lab's docker invocation must parse without error (arity/choices intact).
    ctx = system_test.make_context(
        "system",
        ["--docker", "--with", "all", "--mode", "smoke", "--report", "html"],
    )
    assert ctx.params["target_type"] == "docker"


def test_system_ssh_argv_parses():
    ctx = system_test.make_context(
        "system",
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
        ctx = system_test.make_context("system", ["--docker", flag, "git"])
        assert ctx.params["deploy_from"] == "git"
