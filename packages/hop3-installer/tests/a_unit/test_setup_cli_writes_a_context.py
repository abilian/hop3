# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The deployer must point the local CLI at the server using the canonical writer.

It ran `hop3 settings set server <url>` with `capture_output=True`. That command
is deprecated and says so on stderr — discarded — and it writes `api_url` into
config.toml, which `Config.get_api_url` consults *last*, below every context. So
an operator with any context configured was told "CLI configured to connect to
<host>" and then had every command go somewhere else entirely.

It also logged that success line unconditionally: after a failed token fetch,
after a failed write, always.

Scope narrowed since: only a `--docker` deploy configures the CLI. An SSH
deploy leaves it alone, because the address worth recording for a real server
is `https://<admin-domain>` and deciding whether that is reachable — or
whether to tunnel — is `hop3 login`'s job, not a second implementation here.
And the context is no longer `default`: passing `--context default` skipped
the guard that refuses to move an operator's `default` onto another server.
"""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest
from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import CLI_CONTEXT_NAME, Deployer

# `hop3_installer.deployer.deploy` the *module*: the package binds that name to a
# function, so the usual `from ... import deploy` hands back the wrong object.
deploy_mod = sys.modules["hop3_installer.deployer.deploy"]


class _Backend:
    """Answers `admin:create` and `admin:token` the way a live server would."""

    def __init__(self, *, token: str | None = "eyJhbGciOi.payload.sig") -> None:
        self.token = token
        self.commands: list[str] = []

    def run(self, cmd, check=False, stdin=None):
        self.commands.append(cmd)
        if "admin:token" in cmd and self.token is not None:
            return SimpleNamespace(
                success=True, stdout=f"{self.token}\n", stderr="", returncode=0
            )
        if "admin:token" in cmd:
            return SimpleNamespace(
                success=False, stdout="", stderr="boom", returncode=1
            )
        return SimpleNamespace(success=True, stdout="", stderr="", returncode=0)


@pytest.fixture
def spawned(monkeypatch):
    """Capture the argv of every local process the deployer spawns."""
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy_mod.subprocess, "run", fake_run)
    return calls


def make_deployer(backend: _Backend, **cfg) -> Deployer:
    # Not quiet: `log` prints warnings only when quiet is off, and the failure
    # paths below are exactly what must be visible.
    #
    # Docker by default: that is the only target this step still acts on.
    settings = {"host": "server.example.com", "use_docker": True, **cfg}
    return Deployer(DeployConfig(**settings), backend=backend)  # type: ignore[arg-type]


def test_writes_through_hop3_login_into_a_named_context(spawned):
    assert make_deployer(_Backend())._setup_cli()

    assert len(spawned) == 1, "one local command, not two `settings set` calls"
    argv = spawned[0]
    assert argv[:2] == ["hop3", "login"]
    assert "--context" in argv
    assert argv[argv.index("--context") + 1] == CLI_CONTEXT_NAME
    assert argv[argv.index("--url") + 1] == "http://localhost:8000"
    assert argv[argv.index("--token") + 1].startswith("eyJ")


def test_the_context_is_never_the_operators_default(spawned):
    """
    `--context default` skips `hop3 login`'s own guard, which refuses to
    repoint an existing `default` at a different server. A deploy silently
    moving the CLI's default target onto the box being deployed is the
    "hop3 apps reports on the wrong machine" failure that guard exists for.
    """
    assert CLI_CONTEXT_NAME != "default"

    make_deployer(_Backend())._setup_cli()

    argv = spawned[0]
    assert argv[argv.index("--context") + 1] != "default"


def test_an_ssh_deploy_leaves_the_local_cli_alone(spawned):
    """
    It used to point the CLI at `http://<host>:8000` — the API port, in
    clear, on a socket bound to every interface, carrying a bearer token.
    The banner gives `hop3 login <target>` instead, which negotiates HTTPS
    or a tunnel and says which.
    """
    assert make_deployer(_Backend(), use_docker=False)._setup_cli()

    assert spawned == []


def test_the_deprecated_settings_command_is_never_invoked(spawned):
    make_deployer(_Backend())._setup_cli()
    assert not any("settings" in argv for argv in spawned)


def test_docker_targets_loopback_not_the_ambient_host(spawned):
    """`--docker` deployed to the container; the ambient host is not the target."""
    make_deployer(_Backend(), use_docker=True)._setup_cli()
    argv = spawned[0]
    assert argv[argv.index("--url") + 1] == "http://localhost:8000"


def test_no_token_means_no_login_and_no_success_claim(spawned, capsys):
    assert not make_deployer(_Backend(token=None))._setup_cli()
    assert spawned == [], "must not claim to log in without a token"
    assert "CLI configured" not in capsys.readouterr().out


def test_a_failed_login_is_not_reported_as_success(monkeypatch, capsys):
    def failing(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, returncode=1, stdout="", stderr="connection refused"
        )

    monkeypatch.setattr(deploy_mod.subprocess, "run", failing)
    assert not make_deployer(_Backend())._setup_cli(), "the deploy must fail"
    out = capsys.readouterr().out
    assert "CLI configured" not in out
    assert "connection refused" in out


def test_a_missing_cli_is_reported_not_crashed(monkeypatch, capsys):
    def missing(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(deploy_mod.subprocess, "run", missing)
    assert not make_deployer(_Backend())._setup_cli()
    assert "hop3 CLI not found" in capsys.readouterr().out
