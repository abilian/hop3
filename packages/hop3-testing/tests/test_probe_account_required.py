# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A recipe that creates a probe account fails its test when the account is missing.

The deploy carries on past a failed ``[probe].create``, and the check then signs
in as the operator. Six published recipes passed that way, their probe commands
broken, through a whole run.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from hop3_testing.apps.catalog import AppSource
from hop3_testing.runners.deployment import DeploymentTestRunner

if TYPE_CHECKING:
    from pathlib import Path

_PROBE = '[probe]\ncreate = "gitea admin user create --username hop3probe"\n'
_DEPLOY_LOG = (
    "-----> Creating the Hop3 probe account...\n"
    "  Could not create the probe account for 'gitea-1': exit status 1: "
    "Unable to load config file\n"
)


class _Server:
    """Answers the probe reader with what the server recorded."""

    def __init__(self, recorded: str) -> None:
        self.recorded = recorded
        self.commands: list[str] = []

    def exec_run(self, cmd: str) -> tuple[int, str, str]:
        self.commands.append(cmd)
        return 0, self.recorded, ""


def _error(tmp_path: Path, hop3_toml: str, server: _Server) -> str | None:
    (tmp_path / "hop3.toml").write_text('[metadata]\nid = "gitea"\n' + hop3_toml)
    session = SimpleNamespace(
        app=AppSource(name="gitea", path=tmp_path),
        app_name="gitea-1",
        last_deploy_output=_DEPLOY_LOG,
    )
    runner = DeploymentTestRunner(target=cast("Any", server), cleanup=True)
    return runner._probe_account_error(cast("Any", session))


def test_a_probe_the_server_never_recorded_fails_with_the_deploys_reason(tmp_path):
    error = _error(tmp_path, _PROBE, _Server(recorded="\n"))

    assert error is not None
    assert "did not create the probe account" in error
    assert "Unable to load config file" in error


def test_a_recorded_probe_passes(tmp_path):
    assert _error(tmp_path, _PROBE, _Server(recorded="created\n")) is None


def test_a_recipe_without_a_probe_command_is_not_asked(tmp_path):
    server = _Server(recorded="")

    assert _error(tmp_path, '[probe]\nusername = "x"\n', server) is None
    assert server.commands == []


def test_the_reader_survives_its_shell_quoting(tmp_path):
    """It travels inside `su - hop3 -c "… python -c \\"…\\""`."""
    server = _Server(recorded="created")
    _error(tmp_path, _PROBE, server)
    (command,) = server.commands
    snippet = command.split('-c \\"', 1)[1].rsplit('\\"', 1)[0]

    assert not set('"$`') & set(snippet)
    compile(snippet, "<reader>", "exec")
