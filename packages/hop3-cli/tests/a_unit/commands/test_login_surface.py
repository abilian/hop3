# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The login surface names one axis: which client receives a credential.

`--ssh` named a transport and `--web` a destination, so they read as
alternatives on one axis while sitting on two — and both travel over SSH
anyway, which is why repeating `root@host` in each made them look like a pair.
The target is positional now, `--browser` says which client, and both old
spellings still dispatch.
"""

from __future__ import annotations

import pytest
from hop3_cli.commands.local import login_cmd
from hop3_cli.commands.local.context_cmd import context_add
from hop3_cli.commands.local.login_cmd import (
    _parse_login_ssh_args,
    _parse_login_web_args,
    is_browser_form,
    ssh_target_argument,
)
from hop3_cli.config import Config

TARGET = "root@prod.example.com"


class TestTheTargetIsPositional:
    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            ([TARGET], TARGET),
            (["prod.example.com"], "prod.example.com"),
            (["root@prod.example.com:2222"], "root@prod.example.com:2222"),
            (["--ssh", TARGET], TARGET),  # the old spelling
            (["--browser", TARGET], TARGET),
            (["--web", TARGET], TARGET),
        ],
    )
    def test_recognised(self, args, expected):
        assert ssh_target_argument(args) == expected

    @pytest.mark.parametrize(
        "args",
        [
            [],
            ["--browser"],
            ["--username", "admin"],  # a flag's value is not the target
            ["--token", "eyJ", "--url", "https://h"],
            ["https://h?token=x"],  # a URL is handled by the token form
            ["https://prod.example.com"],
        ],
    )
    def test_not_a_target(self, args):
        assert ssh_target_argument(args) is None

    def test_a_flag_value_is_never_taken_as_the_target(self):
        """`--username admin` must not make `admin` the host."""
        assert ssh_target_argument(["--username", "admin"]) is None
        assert ssh_target_argument(["--username", "admin", TARGET]) == TARGET


class TestOldSpellingsStillDispatch:
    """Rename behind an alias; the alias has to keep working."""

    @pytest.mark.parametrize("flag", ["--browser", "--web"])
    def test_browser_flags(self, flag):
        assert is_browser_form([flag]) is True
        assert is_browser_form([flag, TARGET]) is True

    def test_the_positional_form_is_not_the_browser_form(self):
        assert is_browser_form([TARGET]) is False

    def test_ssh_flag_still_parses(self):
        target, *_ = _parse_login_ssh_args(["--ssh", TARGET])
        assert target == TARGET

    def test_the_positional_form_parses_the_same(self):
        target, *_ = _parse_login_ssh_args([TARGET])
        assert target == TARGET

    def test_a_valueless_ssh_flag_still_reaches_the_ssh_form(self, monkeypatch):
        """
        `hop3 login --ssh` names no target, so the positional parser finds none.

        Without the explicit `--ssh` arm it would fall through to the password
        prompt, which answers a different question than the one asked.
        """
        calls: list[str] = []
        for name in ("web", "ssh", "token", "password"):
            monkeypatch.setattr(
                login_cmd,
                f"handle_login_{name}",
                lambda *_a, _n=name, **_k: calls.append(_n),
            )
        login_cmd.handle_login(["--ssh"], Config(data={}), None)
        assert calls == ["ssh"]

    def test_a_missing_target_is_refused_with_the_new_spelling(self, capsys):
        with pytest.raises(SystemExit):
            _parse_login_ssh_args(["--username", "admin"])
        assert "hop3 login root@server.com" in capsys.readouterr().err


class TestBrowserTargetIsOptional:
    def test_bare_browser_uses_the_current_context(self, monkeypatch):
        monkeypatch.setattr(login_cmd, "_get_ssh_target_from_config", lambda _c: TARGET)
        target, username = _parse_login_web_args(["--browser"], Config(data={}))
        assert target == TARGET
        assert username == "admin"

    def test_an_explicit_target_works_before_any_context(self, monkeypatch):
        monkeypatch.setattr(login_cmd, "_get_ssh_target_from_config", lambda _c: None)
        target, _ = _parse_login_web_args(["--browser", TARGET], Config(data={}))
        assert target == TARGET

    def test_a_bare_host_becomes_root(self, monkeypatch):
        monkeypatch.setattr(login_cmd, "_get_ssh_target_from_config", lambda _c: None)
        target, _ = _parse_login_web_args(
            ["--browser", "prod.example.com"], Config(data={})
        )
        assert target == "root@prod.example.com"

    def test_neither_names_both_forms(self, monkeypatch, capsys):
        monkeypatch.setattr(login_cmd, "_get_ssh_target_from_config", lambda _c: None)
        with pytest.raises(SystemExit) as excinfo:
            _parse_login_web_args(["--browser"], Config(data={}))
        assert excinfo.value.code != 0
        err = capsys.readouterr().err
        assert "hop3 login --browser root@server.com" in err
        assert "hop3 login root@server.com" in err

    def test_username_is_honoured(self, monkeypatch):
        monkeypatch.setattr(login_cmd, "_get_ssh_target_from_config", lambda _c: None)
        _, username = _parse_login_web_args(
            ["--browser", TARGET, "--username", "alice"], Config(data={})
        )
        assert username == "alice"


class TestDispatch:
    """The whole point: which handler each form reaches."""

    @pytest.fixture
    def routed(self, monkeypatch):
        calls: list[str] = []
        for name in ("web", "ssh", "token", "password"):
            monkeypatch.setattr(
                login_cmd,
                f"handle_login_{name}",
                lambda *_a, _n=name, **_k: calls.append(_n),
            )
        return calls

    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            ([TARGET], "ssh"),
            (["prod.example.com"], "ssh"),
            (["--ssh", TARGET], "ssh"),
            (["--browser"], "web"),
            (["--browser", TARGET], "web"),
            (["--web", TARGET], "web"),
            (["--token", "eyJ", "--url", "https://h"], "token"),
            ([], "password"),
            (["--username", "alice"], "password"),
        ],
    )
    def test_routes(self, routed, args, expected):
        login_cmd.handle_login(list(args), Config(data={}), None)
        assert routed == [expected]

    def test_the_browser_form_wins_over_its_target(self, routed):
        """`--browser root@h` is a dashboard link, not a CLI login."""
        login_cmd.handle_login(["--browser", TARGET], Config(data={}), None)
        assert routed == ["web"]


class TestANamedContextSignsInThroughItsRoute:
    """`hop3 login --context dev` asked for a username, though `dev` was ssh://."""

    @pytest.fixture
    def ssh_args(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(
            login_cmd, "handle_login_ssh", lambda args, *_a: calls.append(args)
        )
        monkeypatch.setattr(
            login_cmd, "handle_login_password", lambda *_a: calls.append(["password"])
        )
        return calls

    def _config(self, tmp_path, **contexts: dict[str, str]) -> Config:
        config = Config(data={"contexts": contexts}, config_file=tmp_path / "c.toml")
        config.set_context_override("dev")
        return config

    def test_an_ssh_server(self, ssh_args, tmp_path):
        config = self._config(tmp_path, dev={"server": "ssh://admin@dev.example:2222"})
        login_cmd.handle_login([], config, None)
        assert ssh_args == [["admin@dev.example:2222"]]

    def test_an_https_server_with_a_bootstrap_route(self, ssh_args, tmp_path):
        config = self._config(
            tmp_path,
            dev={"server": "https://dev.example", "bootstrap": "ssh://dev.example"},
        )
        login_cmd.handle_login([], config, None)
        assert ssh_args == [["root@dev.example"]]

    def test_no_route_is_still_the_password_form(self, ssh_args, tmp_path):
        config = self._config(tmp_path, dev={"server": "https://dev.example"})
        login_cmd.handle_login([], config, None)
        assert ssh_args == [["password"]]

    def test_a_username_asks_for_the_password_form(self, ssh_args, tmp_path):
        config = self._config(tmp_path, dev={"server": "ssh://root@dev.example"})
        login_cmd.handle_login(["--username", "alice"], config, None)
        assert ssh_args == [["password"]]


class TestContextAddCarriesABootstrapRoute:
    """
    Without this, a context on https:// could be declared but never renew.

    Phase 2 gave contexts a bootstrap field and taught renewal to use it, but
    only `hop3 login` wrote one — so a hand-declared https context fell back to
    "run hop3 login", which is correct and unhelpful.
    """

    def test_a_global_context_records_it(self, tmp_path, capsys):
        config = Config(data={}, config_file=tmp_path / "config.toml")
        context_add(
            ["prod", "--server", "https://prod.example.com", "--bootstrap",
             f"ssh://{TARGET}", "--global"],
            config,
        )  # fmt: skip
        assert config.get_context_server("prod") == "https://prod.example.com"
        assert config.get_context_bootstrap("prod") == f"ssh://{TARGET}"
        assert "token renewal over" in capsys.readouterr().out

    def test_it_is_optional(self, tmp_path):
        config = Config(data={}, config_file=tmp_path / "config.toml")
        context_add(["prod", "--server", f"ssh://{TARGET}", "--global"], config)
        # An ssh:// server bootstraps through itself; no second copy is written.
        assert config.get_context_bootstrap("prod") == f"ssh://{TARGET}"

    def test_a_non_ssh_bootstrap_is_refused(self, tmp_path, capsys):
        config = Config(data={}, config_file=tmp_path / "config.toml")
        with pytest.raises(SystemExit) as excinfo:
            context_add(
                ["prod", "--server", "https://p", "--bootstrap", "https://p",
                 "--global"],
                config,
            )  # fmt: skip
        assert excinfo.value.code != 0
        assert "must be an ssh:// address" in capsys.readouterr().err


class TestLoginOutput:
    """
    One line, carrying all three facts a reader needs.

    Who, where, and under which name — the name being the one that `hop3 apps
    --context <?>` otherwise leaves you to guess.
    """

    def test_names_user_server_and_context(self, capsys):
        login_cmd._print_login_success("admin", "https://prod.example.com", "prod")
        out = capsys.readouterr().out
        assert "admin" in out
        assert "https://prod.example.com" in out
        assert "context 'prod'" in out

    def test_is_one_line(self, capsys):
        login_cmd._print_login_success("admin", "https://p.example.com", "default")
        body = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert len(body) == 1, body
