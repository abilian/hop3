# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Where a command goes (ADR 042, rules B and C).

`--context` > `HOP3_CONTEXT` (or `HOP3_API_URL`) > the checkout's binding
(inside a project) > the global current context (outside one). A name
resolves or aborts; a project with no binding refuses; a project's
`[contexts.*]` blocks name no server and, when present, must include the
chosen context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from hop3_cli.commands.local.login_cmd import record_server_login
from hop3_cli.config import DEFAULT_CONTEXT_NAME, Config
from hop3_cli.core import credential_store as cs
from hop3_cli.core.resolution import ContextSource, resolve_context
from hop3_cli.core.target import Target, resolve_target
from hop3_cli.exceptions import TargetError
from hop3_cli.main import run_command_from_args

if TYPE_CHECKING:
    from pathlib import Path

DEV = "https://dev.example.com"
PROD = "https://prod.example.com"


@pytest.fixture
def config(tmp_path: Path) -> Config:
    cfg = Config(data={}, config_file=tmp_path / "config.toml")
    cfg.set_context_server("dev", DEV)
    cfg.set_context_server("prod", PROD, bootstrap="ssh://root@prod.example.com")
    cfg.set_default_context("dev")
    return cfg


def _project(path: Path, toml: str = '[metadata]\nid = "myapp"\n') -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "hop3.toml").write_text(toml)
    return path


def _bind(project: Path, name: str) -> None:
    (project / ".hop3-local.toml").write_text(f'[local]\ncontext = "{name}"\n')


def _target(config: Config, cli_context: str | None = None) -> Target:
    resolution = resolve_context(
        cli_context, default_context=config.get_default_context()
    )
    return resolve_target(resolution, config)


# ---- rule B ---------------------------------------------------------------


def test_outside_a_project_the_global_context_is_used(config):
    target = _target(config)
    assert (target.context, target.server) == ("dev", DEV)
    assert target.source is ContextSource.GLOBAL


def test_the_flag_outranks_everything(config, tmp_path, monkeypatch):
    project = _project(tmp_path / "app")
    _bind(project, "dev")
    monkeypatch.chdir(project)
    monkeypatch.setenv("HOP3_CONTEXT", "dev")
    target = _target(config, "prod")
    assert (target.context, target.source) == ("prod", ContextSource.FLAG)
    assert target.bootstrap == "ssh://root@prod.example.com"


def test_hop3_context_outranks_the_binding(config, tmp_path, monkeypatch):
    project = _project(tmp_path / "app")
    _bind(project, "dev")
    monkeypatch.chdir(project)
    monkeypatch.setenv("HOP3_CONTEXT", "prod")
    assert _target(config).source is ContextSource.ENV


def test_hop3_api_url_is_the_env_context(config, monkeypatch):
    monkeypatch.setenv("HOP3_API_URL", "http://localhost:8000")
    target = _target(config)
    assert (target.context, target.server) == ("env", "http://localhost:8000")
    assert target.source is ContextSource.ENV_URL


def test_a_bound_checkout_uses_its_binding(config, tmp_path, monkeypatch):
    project = _project(tmp_path / "app")
    _bind(project, "prod")
    monkeypatch.chdir(project)
    target = _target(config)
    assert (target.context, target.source) == ("prod", ContextSource.BINDING)


def test_the_binding_is_read_from_a_subdirectory(config, tmp_path, monkeypatch):
    project = _project(tmp_path / "app")
    _bind(project, "prod")
    (project / "src").mkdir()
    monkeypatch.chdir(project / "src")
    assert _target(config).context == "prod"


def test_a_binding_above_the_project_does_not_apply(config, tmp_path, monkeypatch):
    _bind(tmp_path, "prod")
    monkeypatch.chdir(_project(tmp_path / "app"))
    with pytest.raises(TargetError, match="not bound"):
        _target(config)


# ---- refusals -------------------------------------------------------------


def test_an_unbound_checkout_refuses_and_says_how_to_bind(
    config, tmp_path, monkeypatch
):
    """The global context must never reach a project nobody bound."""
    monkeypatch.chdir(_project(tmp_path / "app"))
    with pytest.raises(TargetError) as exc:
        _target(config)
    message = str(exc.value)
    assert "not bound" in message
    assert "hop3 context use <name>" in message
    assert "dev, prod" in message


def test_an_unknown_name_aborts_whatever_supplied_it(config, monkeypatch):
    monkeypatch.setenv("HOP3_CONTEXT", "gone")
    with pytest.raises(TargetError, match=r"'gone' .*from HOP3_CONTEXT.* not defined"):
        _target(config)


def test_a_binding_to_a_removed_context_aborts(config, tmp_path, monkeypatch):
    project = _project(tmp_path / "app")
    _bind(project, "staging")
    monkeypatch.chdir(project)
    with pytest.raises(TargetError, match=r"'staging' .*bound in this checkout"):
        _target(config)


def test_no_context_and_no_server_says_how_to_sign_in(tmp_path):
    with pytest.raises(TargetError, match="hop3 login <user>@<host>"):
        _target(Config(data={}, config_file=tmp_path / "c.toml"))


def test_an_explicit_name_and_a_different_api_url_conflict(config, monkeypatch):
    monkeypatch.setenv("HOP3_API_URL", "http://elsewhere:8000")
    with pytest.raises(TargetError, match="HOP3_API_URL"):
        _target(config, "prod")


def test_an_explicit_name_matching_the_api_url_is_fine(config, monkeypatch):
    monkeypatch.setenv("HOP3_API_URL", PROD)
    assert _target(config, "prod").server == PROD


# ---- the project's [contexts.*] blocks ------------------------------------


def test_a_block_with_a_server_is_refused_with_the_replacing_command(
    config, tmp_path, monkeypatch
):
    toml = '[metadata]\nid = "a"\n[contexts.qa]\nserver = "ssh://root@qa"\n'
    project = _project(tmp_path / "app", toml)
    _bind(project, "dev")
    monkeypatch.chdir(project)
    with pytest.raises(TargetError) as exc:
        _target(config)
    assert "hop3 context add qa --server ssh://root@qa" in str(exc.value)


def test_a_context_matching_no_block_is_refused(config, tmp_path, monkeypatch):
    toml = '[metadata]\nid = "a"\n[contexts.prod]\napp = "a-prod"\n'
    project = _project(tmp_path / "app", toml)
    _bind(project, "dev")
    monkeypatch.chdir(project)
    with pytest.raises(TargetError, match="matches none of the"):
        _target(config)


def test_a_context_matching_its_block_resolves(config, tmp_path, monkeypatch):
    toml = '[metadata]\nid = "a"\n[contexts.prod]\napp = "a-prod"\n'
    project = _project(tmp_path / "app", toml)
    _bind(project, "prod")
    monkeypatch.chdir(project)
    assert _target(config).context == "prod"


# ---- rule C: the line ------------------------------------------------------


def test_the_line_names_the_context_the_server_and_why(config, tmp_path, monkeypatch):
    project = _project(tmp_path / "app")
    _bind(project, "prod")
    monkeypatch.chdir(project)
    assert _target(config).describe() == f"→ prod ({PROD}), bound in this checkout"


# ---- Config carries the answer --------------------------------------------


def test_config_raises_the_refusal_only_when_a_server_is_needed(config):
    config.set_target_error(TargetError("not bound"))
    assert config.is_configured() is False
    assert config.get_current_context_name() is None
    with pytest.raises(TargetError, match="not bound"):
        config.get_api_url()


def test_config_connects_to_the_target_and_finds_its_token(config):
    config.set_target(Target("prod", PROD, None, ContextSource.FLAG))
    assert config.get_api_url() == PROD
    assert config.get_current_context_name() == "prod"
    assert config.is_authenticated() is False
    cs.set_token(PROD, "eyJtok")
    assert config.get_api_token() == "eyJtok"


# ---- a login records its context and leaves the current one alone ---------


def test_the_first_login_sets_the_global_context(tmp_path, capsys):
    cfg = Config(data={}, config_file=tmp_path / "config.toml")
    record_server_login(cfg, PROD, "eyJtok")
    assert cs.get_token(PROD) == "eyJtok"
    assert cfg.get_context_server(DEFAULT_CONTEXT_NAME) == PROD
    assert cfg.get_default_context() == DEFAULT_CONTEXT_NAME
    assert "now the global current context" in capsys.readouterr().out
    record_server_login(cfg, PROD, "eyJtok2")  # a token refresh says nothing
    assert capsys.readouterr().out.strip() == ""


def test_a_later_login_does_not_switch_the_global_context(config, capsys):
    config.set_context_override("staging")
    record_server_login(config, "https://staging.example.com", "eyJtok")
    assert config.get_default_context() == "dev"
    assert "hop3 context use staging" in capsys.readouterr().out


def test_a_login_to_the_target_records_under_its_name(config):
    config.set_target(Target("prod", PROD, None, ContextSource.BINDING))
    record_server_login(config, PROD, "eyJtok")
    assert config.get_context_server(DEFAULT_CONTEXT_NAME) is None


# ---- through main: the refusal, and the line --------------------------------


def _run(argv: list[str], config: Config) -> list[list[str]]:
    """Run the CLI on ``config``; return the RPC calls it made."""
    calls: list[list[str]] = []
    with (
        patch("hop3_cli.main.load_config", return_value=config),
        patch(
            "hop3_cli.main._execute_rpc_command",
            side_effect=lambda args, *_: calls.append(args),
        ),
    ):
        run_command_from_args(argv)
    return calls


def test_an_unbound_checkout_reaches_no_server(config, tmp_path, monkeypatch):
    monkeypatch.chdir(_project(tmp_path / "app"))
    with pytest.raises(TargetError, match="not bound"):
        _run(["apps"], config)


def test_a_bound_checkout_says_where_it_goes(config, tmp_path, monkeypatch, capsys):
    project = _project(tmp_path / "app")
    _bind(project, "prod")
    monkeypatch.chdir(project)
    cs.set_token(PROD, "eyJtok")
    assert _run(["apps"], config) == [["app", "list"]]  # the alias expanded
    assert f"→ prod ({PROD}), bound in this checkout" in capsys.readouterr().err


def test_quiet_silences_the_line(config, capsys):
    cs.set_token(DEV, "eyJtok")
    _run(["-q", "apps"], config)
    assert "→" not in capsys.readouterr().err


def test_a_login_under_hop3_api_url_never_records_the_env_context(tmp_path):
    cfg = Config(data={}, config_file=tmp_path / "config.toml")
    cfg.set_target(Target("env", "http://localhost:8000", None, ContextSource.ENV_URL))
    record_server_login(cfg, "http://localhost:8000", "eyJtok")
    assert cfg.get_context_server(DEFAULT_CONTEXT_NAME) == "http://localhost:8000"
    assert "env" not in cfg.data["contexts"]
