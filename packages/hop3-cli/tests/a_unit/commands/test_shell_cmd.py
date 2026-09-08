# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 app shell`: the ssh line it builds, and what it refuses."""

from __future__ import annotations

import io
import sys

import pytest
from hop3_cli.commands.local import shell_cmd
from hop3_cli.commands.local.shell_cmd import (
    handle_app_shell,
    remote_shell_command,
    shell_command_args,
    ssh_argv,
)
from hop3_cli.config import Config
from hop3_cli.core.app_scope import is_app_scoped
from hop3_cli.core.ssh_target import SshEndpoint, SshSettings
from hop3_cli.exit_codes import ExitCode


def _config(server: str) -> Config:
    config = Config(data={})
    config.set_active_server(server)
    return config


def test_both_spellings_are_intercepted_and_app_scoped() -> None:
    assert shell_command_args(["app", "shell", "--app", "x"]) == ["--app", "x"]
    assert shell_command_args(["ssh", "--app", "x"]) == ["--app", "x"]
    assert shell_command_args(["app", "run", "--app", "x", "ls"]) is None
    assert is_app_scoped(["app", "shell"]) == (True, 2)
    assert is_app_scoped(["ssh"]) == (True, 1)


def test_remote_command_as_hop3_rides_the_forced_command() -> None:
    assert remote_shell_command("hop3", "myapp") == "app-shell myapp"


def test_remote_command_as_root_switches_to_hop3() -> None:
    assert remote_shell_command("root", "myapp") == (
        "su - hop3 -c '/home/hop3/venv/bin/hop3-server app-shell myapp'"
    )


def _endpoint(**kw) -> SshEndpoint:
    fields = {"host": "srv", "user": "root", "port": 22, "settings": SshSettings()}
    fields.update(kw)
    return SshEndpoint(**fields)


def test_ssh_argv_requests_a_pty_only_with_a_terminal() -> None:
    assert "-t" in ssh_argv(_endpoint(), "app-shell x", tty=True)
    assert "-t" not in ssh_argv(_endpoint(), "app-shell x", tty=False)


def test_ssh_argv_carries_port_key_and_target() -> None:
    endpoint = _endpoint(port=2222, settings=SshSettings(key="/k"))
    argv = ssh_argv(endpoint, "app-shell x", tty=False)
    assert argv[-2:] == ["root@srv", "app-shell x"]
    assert argv[argv.index("-p") + 1] == "2222"
    assert argv[argv.index("-i") + 1] == "/k"


def test_handle_opens_ssh_and_exits_with_its_status(monkeypatch) -> None:
    seen: dict = {}

    def fake_call(argv: list[str]) -> int:
        seen["argv"] = argv
        return 7

    monkeypatch.setattr(shell_cmd.subprocess, "call", fake_call)
    monkeypatch.setattr(sys, "stdin", io.StringIO())  # not a terminal
    with pytest.raises(SystemExit) as exc:
        handle_app_shell(["--app", "myapp"], _config("ssh://root@srv:2222"))
    assert exc.value.code == 7
    assert seen["argv"][-2:] == ["root@srv", remote_shell_command("root", "myapp")]
    assert "-t" not in seen["argv"]
    assert seen["argv"][seen["argv"].index("-p") + 1] == "2222"


def test_handle_refuses_a_stray_positional(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        handle_app_shell(["--app", "myapp", "ls"], _config("ssh://root@srv"))
    assert exc.value.code == ExitCode.USAGE_ERROR
    assert "takes no arguments" in capsys.readouterr().err


def test_handle_refuses_a_name_that_is_not_one_shell_word(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        handle_app_shell(["--app", "my app"], _config("ssh://root@srv"))
    assert exc.value.code == ExitCode.USAGE_ERROR
    assert "invalid app name" in capsys.readouterr().err


def test_handle_refuses_an_http_server(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        handle_app_shell(["--app", "myapp"], _config("http://srv:8000"))
    assert exc.value.code == ExitCode.USAGE_ERROR
    assert "needs an SSH server connection" in capsys.readouterr().err


def test_ssh_argv_passes_the_ssh_options_setting_through() -> None:
    endpoint = _endpoint(settings=SshSettings(options=("ProxyJump=b",)))
    argv = ssh_argv(endpoint, "app-shell x", tty=False)
    assert argv[argv.index("ProxyJump=b") - 1] == "-o"
