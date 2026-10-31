# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The local commands' argv: unknown tokens refused, secrets off the command line.

Each local command walked argv in its own loop ending in ``else: i += 1``, so
`hop3 login root@h --usrname bob` minted a token for the wrong user without a
word. `hop3 login --token` took the JWT only as an argv token, kept by the
shell history and shown by `ps`. `hop3 use` printed a usage error and exited
0, took the app positionally, ignored extra positionals and wrote any name to
`.hop3-app`.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from hop3_cli.commands.local import handle_init, handle_login, handle_use
from hop3_cli.commands.local._argv import parse_local_args
from hop3_cli.commands.local.login_cmd import _parse_token_args
from hop3_cli.config import Config
from hop3_cli.core.resolution import APP_NAME_RE
from hop3_cli.exit_codes import ExitCode
from hop3_cli.ui.rich_printer import RichPrinter

TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.c2lnbmF0dXJl"


class _Stdin(io.StringIO):
    """A piped stdin, or a terminal when ``tty`` is set."""

    def __init__(self, text: str = "", *, tty: bool = False) -> None:
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(data={}, config_file=tmp_path / "config.toml")


def _exit_code(call) -> int | str | None:
    with pytest.raises(SystemExit) as exc:
        call()
    return exc.value.code


class TestTheSharedParser:
    def test_it_reads_values_switches_and_positionals(self):
        parsed = parse_local_args(
            ["host", "--url", "u", "--yes"],
            usage="Usage: x",
            value_flags=frozenset({"--url"}),
            switches=frozenset({"--yes"}),
            max_positionals=1,
        )
        assert parsed.get("--url") == "u"
        assert parsed.switches == {"--yes"}
        assert parsed.positionals == ("host",)

    @pytest.mark.parametrize(
        "args",
        [
            ["--usrname", "bob"],  # a typo'd flag
            ["a", "b"],  # one positional too many
            ["--url"],  # a value flag without its value
            ["--url", "--yes"],  # ...whose next token is another flag
            ["--url", "--tokn"],  # ...or an unknown one, never the value
            ["--url", "a", "--url", "b"],  # a value flag given twice
            ["--yes", "--yes"],  # a switch given twice
            ["--token", "--token"],  # an optional-value flag given twice
            ["--token", "t", "--token", "u"],
            ["--token", "--tokn"],  # an unknown flag is not its value
        ],
    )
    def test_anything_undeclared_is_a_usage_error(self, args, capsys):
        code = _exit_code(
            lambda: parse_local_args(
                args,
                usage="Usage: x",
                value_flags=frozenset({"--url"}),
                optional_value_flags=frozenset({"--token"}),
                switches=frozenset({"--yes"}),
                max_positionals=1,
            )
        )
        assert code == ExitCode.USAGE_ERROR
        assert "Usage: x" in capsys.readouterr().err

    def test_an_optional_value_may_stand_alone(self):
        parsed = parse_local_args(
            ["--token", "--url", "u"],
            usage="Usage: x",
            value_flags=frozenset({"--url"}),
            optional_value_flags=frozenset({"--token"}),
        )
        assert parsed.values == {"--token": None, "--url": "u"}

    def test_a_dash_is_a_value(self):
        parsed = parse_local_args(
            ["--token", "-"],
            usage="Usage: x",
            optional_value_flags=frozenset({"--token"}),
        )
        assert parsed.get("--token") == "-"


class TestUnknownTokensAreRefused:
    @pytest.mark.parametrize(
        "args",
        [
            ["root@h", "--usrname", "bob"],  # ssh form
            ["root@h", "other@h"],  # two targets
            ["--browser", "--usrname", "bob"],  # browser form
            ["--username", "bob", "--pasword"],  # password form
            ["--token", "-", "--uri", "http://h"],  # token form
        ],
    )
    def test_login(self, args, config, monkeypatch):
        monkeypatch.setattr("sys.stdin", _Stdin(TOKEN))
        code = _exit_code(lambda: handle_login(args, config, RichPrinter()))
        assert code == ExitCode.USAGE_ERROR

    def test_init(self, config):
        code = _exit_code(
            lambda: handle_init(["--ssh", "root@h", "--emial", "x"], config, None)
        )
        assert code == ExitCode.USAGE_ERROR


class TestTheTokenStaysOffArgv:
    def test_from_stdin(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", _Stdin(TOKEN + "\n"))
        assert _parse_token_args(["--token", "-", "--url", "http://h"]) == (
            TOKEN,
            "http://h",
        )

    def test_from_a_file(self, tmp_path):
        (tmp_path / "token").write_text(TOKEN + "\n")
        assert _parse_token_args(["--token", f"@{tmp_path / 'token'}"]) == (
            TOKEN,
            None,
        )

    def test_prompted_without_echo_when_omitted(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", _Stdin(tty=True))
        monkeypatch.setattr("getpass.getpass", lambda prompt: TOKEN)
        assert _parse_token_args(["--token", "--url", "http://h"])[0] == TOKEN

    def test_omitted_without_a_terminal_is_refused(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", _Stdin(TOKEN))
        code = _exit_code(lambda: _parse_token_args(["--token"]))
        assert code == ExitCode.USAGE_ERROR
        assert "--token -" in capsys.readouterr().err

    def test_omitted_under_no_input_is_refused(self, monkeypatch):
        monkeypatch.setenv("HOP3_NO_INPUT", "1")
        monkeypatch.setattr("sys.stdin", _Stdin(tty=True))
        assert _exit_code(lambda: _parse_token_args(["--token"])) == 2

    @pytest.mark.parametrize("typed", ["", "   "])
    def test_an_empty_prompted_token_is_refused(self, monkeypatch, capsys, typed):
        monkeypatch.setattr("sys.stdin", _Stdin(tty=True))
        monkeypatch.setattr("getpass.getpass", lambda prompt: typed)
        code = _exit_code(lambda: _parse_token_args(["--token"]))
        assert code == ExitCode.USAGE_ERROR
        assert "empty" in capsys.readouterr().err

    def test_a_prompted_token_is_stripped(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", _Stdin(tty=True))
        monkeypatch.setattr("getpass.getpass", lambda prompt: f"  {TOKEN} ")
        assert _parse_token_args(["--token"])[0] == TOKEN

    def test_an_empty_literal_is_refused(self, capsys):
        code = _exit_code(lambda: _parse_token_args(["--token", ""]))
        assert code == ExitCode.USAGE_ERROR
        err = capsys.readouterr().err
        assert "--token: the value is empty." in err
        assert "shell history" not in err

    def test_an_empty_file_is_refused(self, tmp_path):
        (tmp_path / "token").write_text("\n")
        code = _exit_code(lambda: _parse_token_args(["--token", f"@{tmp_path}/token"]))
        assert code == ExitCode.USAGE_ERROR

    def test_a_literal_still_works_and_says_why_it_should_go(self, capsys):
        assert _parse_token_args(["--token", TOKEN])[0] == TOKEN
        assert "shell history" in capsys.readouterr().err


class TestUse:
    def test_the_app_is_a_flag(self, config):
        config.set_app_override("my-app")
        handle_use([], config, RichPrinter())
        assert Path(".hop3-app").read_text() == "my-app\n"

    def test_the_old_positional_still_dispatches(self, config):
        handle_use(["my-app"], config, RichPrinter())
        assert Path(".hop3-app").read_text() == "my-app\n"

    @pytest.mark.parametrize(
        ("args", "app"),
        [
            (["--clear"], "my-app"),  # --clear with an app
            (["a-app", "b-app"], None),  # a second app
            (["other"], "my-app"),  # named twice
            (["../evil"], None),  # not an app name
            (["--force-it"], None),  # an unknown flag
        ],
    )
    def test_usage_errors_exit_non_zero_and_write_nothing(self, args, app, config):
        config.set_app_override(app)
        code = _exit_code(lambda: handle_use(args, config, RichPrinter()))
        assert code == ExitCode.USAGE_ERROR
        assert not Path(".hop3-app").exists()

    def test_clear(self, config):
        Path(".hop3-app").write_text("my-app\n")
        handle_use(["--clear"], config, RichPrinter())
        assert not Path(".hop3-app").exists()


def test_the_client_app_name_rule_is_the_servers():
    identifiers = pytest.importorskip(
        "hop3.core.identifiers", reason="hop3-server is not installed"
    )
    assert APP_NAME_RE.pattern == identifiers.APP_NAME_RE.pattern
