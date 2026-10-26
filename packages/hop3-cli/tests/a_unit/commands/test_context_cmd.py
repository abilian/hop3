# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for `hop3 context` (ADR 042).

A context is a server, global and personal, in config.toml; `hop3 context`
never edits hop3.toml. `use` and `unset` act on this checkout's binding inside
a project, on the global current context outside one (or with `--global`),
and ask first.

The conftest autouse fixture chdir's into an isolated tmp dir, so `Path.cwd()`
is not a project until a test writes a hop3.toml there.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib
from hop3_cli.commands.flags import CliFlags
from hop3_cli.commands.local.context_cmd import (
    context_add,
    context_list,
    context_remove,
    context_rename,
    context_show,
    context_unset,
    context_use,
)
from hop3_cli.config import Config
from hop3_cli.core.local_overlay import read_binding
from hop3_cli.exit_codes import ExitCode
from hop3_cli.main import _wire_target

DEV = "https://dev.example.com"
PROD = "https://prod.example.com"


@pytest.fixture
def config() -> Config:
    """Two contexts, `dev` the global current one; -y given."""
    cfg = Config(data={}, config_file=Path.cwd() / "config.toml")
    cfg.set_context_server("dev", DEV)
    cfg.set_context_server("prod", PROD)
    cfg.set_default_context("dev")
    cfg.set_assume_yes(True)
    return cfg


def _project(toml: str = '[metadata]\nid = "myapp"\n') -> Path:
    (Path.cwd() / "hop3.toml").write_text(toml)
    return Path.cwd()


def _wired(config: Config) -> Config:
    """Resolve the target as main.py does before dispatching."""
    _wire_target(CliFlags(), config)
    return config


# ---- add / remove / rename: config.toml only ------------------------------


def test_add_records_a_server_and_nothing_else(tmp_path, capsys):
    cfg = Config(data={}, config_file=tmp_path / "config.toml")
    _project()
    before = (Path.cwd() / "hop3.toml").read_text()
    context_add(["qa", "--server", "https://qa.example.com"], cfg)
    assert cfg.get_context_server("qa") == "https://qa.example.com"
    assert (Path.cwd() / "hop3.toml").read_text() == before, "hop3.toml untouched"
    assert "hop3 context use qa" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--domain", "--env"])
def test_add_refuses_what_belongs_to_the_project(config, capsys, flag):
    with pytest.raises(SystemExit):
        context_add(["qa", "--server", "https://qa", flag, "x"], config)
    assert "hop3.toml" in capsys.readouterr().err


def test_add_refuses_an_app(config, capsys):
    config.set_app_override("myapp")
    with pytest.raises(SystemExit):
        context_add(["qa", "--server", "https://qa"], config)
    assert '[contexts.qa] app = "…"' in capsys.readouterr().err


def test_add_requires_a_server(config, capsys):
    with pytest.raises(SystemExit):
        context_add(["qa"], config)
    assert "--server" in capsys.readouterr().err


def test_add_refuses_a_duplicate_and_reserved_names(config, capsys):
    with pytest.raises(SystemExit):
        context_add(["prod", "--server", "https://x"], config)
    with pytest.raises(SystemExit):
        context_add(["env", "--server", "https://x"], config)
    with pytest.raises(SystemExit):
        context_add(["bad name", "--server", "https://x"], config)


def test_remove_says_when_this_checkout_was_bound_to_it(config, capsys):
    project = _project()
    (project / ".hop3-local.toml").write_text('[local]\ncontext = "prod"\n')
    context_remove(["prod"], config)
    assert config.get_context_server("prod") is None
    assert "still bound to 'prod'" in capsys.readouterr().out


def test_rename_carries_the_global_context_and_the_binding(config, capsys):
    project = _project('[metadata]\nid = "a"\n[contexts.dev]\napp = "a-dev"\n')
    (project / ".hop3-local.toml").write_text('[local]\ncontext = "dev"\n')
    context_rename(["dev", "staging"], config)
    assert config.get_context_server("staging") == DEV
    assert config.get_default_context() == "staging"
    assert read_binding(project) == "staging"
    assert "rename the block too" in capsys.readouterr().out


# ---- list / show ----------------------------------------------------------


def test_list_marks_where_a_command_here_goes(config, capsys):
    context_list(_wired(config))
    out = capsys.readouterr().out
    assert f"* dev          {DEV}  (global current context)" in out
    assert f"  prod         {PROD}" in out
    assert "Here: dev" in out


def test_list_in_an_unbound_project_says_so(config, capsys):
    _project()
    context_list(_wired(config))
    assert "not bound to a context" in capsys.readouterr().out


def test_show_includes_the_projects_block(config, capsys):
    _project('[metadata]\nid = "a"\n[contexts.prod]\napp = "a-prod"\n')
    context_show(["prod"], config)
    out = capsys.readouterr().out
    assert f"server:     {PROD}" in out
    assert "app:      a-prod" in out


def test_show_unknown(config, capsys):
    with pytest.raises(SystemExit) as exc:
        context_show(["nope"], config)
    assert exc.value.code == ExitCode.RESOLUTION_ERROR
    assert "known: dev, prod" in capsys.readouterr().err


# ---- use / unset ----------------------------------------------------------


def test_use_inside_a_project_binds_the_checkout(config, capsys):
    project = _project()
    context_use(["prod"], config)
    assert read_binding(project) == "prod"
    assert config.get_default_context() == "dev", "the global context is untouched"
    assert "Bound" in capsys.readouterr().out


def test_use_outside_a_project_sets_the_global_context(config):
    context_use(["prod"], config)
    assert config.get_default_context() == "prod"


def test_use_global_inside_a_project_leaves_the_binding(config, capsys):
    project = _project()
    context_use(["--global", "prod"], config)
    assert config.get_default_context() == "prod"
    assert read_binding(project) is None
    assert "its binding still decides" in capsys.readouterr().out


def test_use_refuses_an_unknown_context(config, capsys):
    with pytest.raises(SystemExit) as exc:
        context_use(["nope"], config)
    assert exc.value.code == ExitCode.RESOLUTION_ERROR


def test_use_refuses_a_context_matching_no_block(config, capsys):
    _project('[metadata]\nid = "a"\n[contexts.prod]\napp = "a-prod"\n')
    with pytest.raises(SystemExit):
        context_use(["dev"], config)
    assert "matches none of the" in capsys.readouterr().err


def test_use_asks_naming_the_scope_and_the_address(config, monkeypatch):
    project = _project()
    config.set_assume_yes(False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    asked: list[str] = []
    monkeypatch.setattr(
        "builtins.input", lambda question: asked.append(question) or "n"
    )
    with pytest.raises(SystemExit) as exc:
        context_use(["prod"], config)
    assert exc.value.code == ExitCode.CONFIRMATION_DECLINED
    assert asked == [f"Bind this checkout ({project}) to 'prod' ({PROD})? [y/N] "]
    assert read_binding(project) is None, "a no writes nothing"


def test_use_without_a_terminal_refuses_unless_yes(config, monkeypatch, capsys):
    _project()
    config.set_assume_yes(False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit) as exc:
        context_use(["prod"], config)
    assert exc.value.code == ExitCode.CONFIRMATION_DECLINED
    assert "--yes" in capsys.readouterr().err


def test_unset_removes_the_binding(config):
    project = _project()
    context_use(["prod"], config)
    context_unset([], config)
    assert read_binding(project) is None
    assert not (project / ".hop3-local.toml").exists()


def test_unset_keeps_the_overlays_other_keys(config):
    project = _project()
    (project / ".hop3-local.toml").write_text(
        '[local]\ncontext = "prod"\n[other]\nkey = "v"\n'
    )
    context_unset([], config)
    assert tomllib.loads((project / ".hop3-local.toml").read_text()) == {
        "other": {"key": "v"}
    }


def test_unset_outside_a_project_clears_the_global_context(config):
    context_unset([], config)
    assert config.get_default_context() is None
