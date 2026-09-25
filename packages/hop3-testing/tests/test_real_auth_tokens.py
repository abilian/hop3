# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Real-auth test tokens: the harness authenticates instead of bypassing.

The harness never sets ``HOP3_UNSAFE`` to disable authentication. It fetches a
token for a real admin account from the target, running ``hop3-server
admin:ssh-token`` as ``hop3 login --ssh`` does. It used to mint a token for an
account that did not exist, which role checks (ADR 061) refuse.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hop3_cli.commands.local.ssh_ops import SSH_TOKEN_COMMAND, as_hop3_user
from hop3_testing.exceptions import ConfigurationError
from hop3_testing.targets.base import TargetInfo
from hop3_testing.targets.constants import hermetic_cli_cwd, hermetic_cli_env
from hop3_testing.targets.helpers import CommandResult, fetch_api_token

TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJhZG1pbiIsInNjb3BlcyI6WyJhZG1pbiJdfQ"
    ".c2lnbmF0dXJlLWJ5dGVzLW9mLWEtcmVhbC10b2tlbg"
)


def test_hermetic_cli_env_strips_steering_vars(monkeypatch):
    """
    The harness must not be steered by ambient HOP3_* vars — a leaked
    HOP3_DEV_MODE/HOP3_CONTEXT/HOP3_API_TOKEN in the launch environment (e.g. the
    testlab worker's app-runtime env) would silently redirect the deploy and 401.
    Regression for the testlab/hop3-test seam.
    """
    for var in (
        "HOP3_DEV_MODE",
        "HOP3_CONTEXT",
        "HOP3_API_TOKEN",
        "HOP3_API_URL",
        "HOP3_CONFIG_DIR",
        "HOP3_DEV_HOST",
        "HOP3_APP",
    ):
        monkeypatch.setenv(var, "leaked")
    monkeypatch.setenv("PATH", "/usr/bin")  # a non-steering var must survive

    env = hermetic_cli_env()

    assert "HOP3_DEV_MODE" not in env
    assert "HOP3_CONTEXT" not in env
    assert "HOP3_API_TOKEN" not in env
    assert "HOP3_CONFIG_DIR" not in env
    assert env.get("PATH") == "/usr/bin"


class _Target:
    """A CommandRunner stand-in that records what it was asked to run."""

    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.result = CommandResult(stdout=stdout, stderr=stderr, returncode=returncode)
        self.commands: list[str] = []

    def run(self, command: str, *, check: bool = False) -> CommandResult:
        self.commands.append(command)
        return self.result


def test_the_token_comes_from_admin_ssh_token_run_as_hop3():
    """The same invocation `hop3 login --ssh` uses, not a copy of it."""
    target = _Target(stdout=f"{TOKEN}\n")

    assert fetch_api_token(target) == TOKEN
    assert target.commands == [as_hop3_user(SSH_TOKEN_COMMAND)]


def test_no_token_is_a_loud_failure():
    """Never fall back to calling the API unauthenticated."""
    target = _Target(stdout="", returncode=1, stderr="su: user hop3 does not exist")

    with pytest.raises(ConfigurationError, match="printed no token") as excinfo:
        fetch_api_token(target)
    assert "su: user hop3 does not exist" in str(excinfo.value)


def test_a_target_with_an_api_but_no_token_refuses():
    info = TargetInfo(ssh_host="localhost", ssh_port=22, api_url="http://x:8000")

    with pytest.raises(ConfigurationError, match="no API token"):
        info.require_api_token()


def test_hermetic_cli_cwd_is_empty_and_cached():
    """
    The harness runs every `hop3` from a dir with no hop3.toml, so a stray
    hop3.toml in the test runner's CWD (e.g. the repo root) can't trigger the
    CLI's project-mismatch guard and refuse a deploy/destroy.
    """
    first = hermetic_cli_cwd()
    assert hermetic_cli_cwd() == first  # cached: one shared dir

    d = Path(first)
    assert d.is_dir()
    assert not (d / "hop3.toml").exists()
    assert list(d.iterdir()) == []  # freshly-made, empty
