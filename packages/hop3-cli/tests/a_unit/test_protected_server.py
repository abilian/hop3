# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The CLI's half of protected servers (ADR 042, rule D).

The server refuses a change it was not named for explicitly, and asks for a
confirmation otherwise; it learns how the context was chosen from
`context_source`. The CLI sends that, asks for the app's name typed when the
server asks, resends with `protected_confirmed`, and remembers the mark.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hop3_cli.config import Config
from hop3_cli.core.resolution import ContextSource
from hop3_cli.core.target import Target
from hop3_cli.exit_codes import ExitCode
from hop3_cli.main import _execute_rpc_command
from hop3_cli.rpc.client import Client
from hop3_cli.rpc.errors import PROTECTED_NEEDS_CONFIRMATION
from hop3_cli.ui import RichPrinter
from jsonrpcclient import Error, Ok

if TYPE_CHECKING:
    from pathlib import Path

PROD = "https://prod.example.com"
ARGV = ["env", "set", "--app", "myapp", "A=1"]


@pytest.fixture
def config(tmp_path: Path) -> Config:
    cfg = Config(data={}, config_file=tmp_path / "config.toml")
    cfg.set_context_server("prod", PROD)
    cfg.set_target(Target("prod", PROD, None, ContextSource.FLAG))
    return cfg


class _Server:
    """Answers like a protected server, recording what each call sent."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def __call__(self, client: Client, method: str, cli_args, **extra) -> object:
        target = client.config.get_target()
        self.sent.append({
            "source": target.source.name.lower() if target else None,
            "confirmed": client.protected_confirmed,
        })
        if not client.protected_confirmed:
            return Error(403, "protected", {"kind": PROTECTED_NEEDS_CONFIRMATION}, 1)
        return Ok([], 1)


@pytest.fixture
def printer() -> RichPrinter:
    return RichPrinter()


@pytest.fixture
def server(monkeypatch) -> _Server:
    fake = _Server()
    monkeypatch.setattr(
        Client,
        "_do_rpc",
        lambda client, method, cli_args, **extra: fake(client, method, cli_args),
    )
    monkeypatch.setattr("hop3_cli.main.handle_response", lambda *a, **k: None)
    return fake


def test_the_typed_app_name_confirms_and_the_call_is_resent(
    config, server, monkeypatch, printer
):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    asked: list[str] = []
    monkeypatch.setattr("builtins.input", lambda q: asked.append(q) or "myapp")

    _execute_rpc_command(ARGV, config, {}, printer)

    assert server.sent == [
        {"source": "flag", "confirmed": False},
        {"source": "flag", "confirmed": True},
    ]
    assert "Type the app's name (myapp)" in asked[0]
    assert config.is_context_protected("prod")


def test_a_wrong_name_changes_nothing(config, server, monkeypatch, printer):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda q: "other")
    with pytest.raises(SystemExit) as exc:
        _execute_rpc_command(ARGV, config, {}, printer)
    assert exc.value.code == ExitCode.CONFIRMATION_DECLINED
    assert len(server.sent) == 1, "nothing resent"


def test_yes_answers_the_question(config, server, printer):
    config.set_assume_yes(True)
    _execute_rpc_command(ARGV, config, {}, printer)
    assert server.sent[-1] == {"source": "flag", "confirmed": True}


def test_without_a_terminal_it_refuses(config, server, monkeypatch, printer):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit) as exc:
        _execute_rpc_command(ARGV, config, {}, printer)
    assert exc.value.code == ExitCode.CONFIRMATION_DECLINED
