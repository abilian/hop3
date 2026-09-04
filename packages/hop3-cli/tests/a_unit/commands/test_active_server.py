# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the v2 connection path (ADR 042 r2, step C2).

When a context resolves to a `[contexts.<name>].server` in the project hop3.toml,
that address becomes `config._active_server`, and the connection (url + token)
flows from it + the per-server token store — not the legacy config.toml context.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from hop3_cli.commands.local.login_cmd import record_server_login
from hop3_cli.config import Config
from hop3_cli.core import credential_store as cs
from hop3_cli.exit_codes import ExitCode
from hop3_cli.main import (
    _abort_if_env_url_shadows_context,
    _compute_resolutions,
    _require_context_server,
    _resolve_active_server,
)

ADDR = "ssh://root@prod.example.com"


def _ctx_res(context: str | None) -> SimpleNamespace:
    return SimpleNamespace(context=context)


def _write_toml(text: str) -> None:
    (Path.cwd() / "hop3.toml").write_text(text)


# ---- _resolve_active_server: context name -> server (project, then global) ----


def test_resolve_active_server_from_hop3_toml():
    _write_toml(f'[metadata]\nid="a"\n[contexts.prod]\nserver="{ADDR}"\n')
    assert _resolve_active_server(_ctx_res("prod"), Config(data={})) == ADDR


def test_resolve_active_server_from_global_context():
    # No project context here; the name resolves from a global config.toml context.
    cfg = Config(data={"contexts": {"prod": {"server": ADDR}}})
    assert _resolve_active_server(_ctx_res("prod"), cfg) == ADDR


def test_resolve_active_server_project_wins_over_global():
    _write_toml(f'[metadata]\nid="a"\n[contexts.prod]\nserver="{ADDR}"\n')
    cfg = Config(data={"contexts": {"prod": {"server": "ssh://global"}}})
    assert _resolve_active_server(_ctx_res("prod"), cfg) == ADDR  # project first


def test_resolve_active_server_none_when_no_context():
    assert _resolve_active_server(None, Config(data={})) is None
    assert _resolve_active_server(_ctx_res(None), Config(data={})) is None


def test_resolve_active_server_unknown_or_serverless():
    _write_toml('[metadata]\nid="a"\n[contexts.prod]\nserver="x"\n')
    assert _resolve_active_server(_ctx_res("dev"), Config(data={})) is None  # unknown
    _write_toml('[metadata]\nid="a"\n[contexts.prod]\napp="a"\n')
    assert (
        _resolve_active_server(_ctx_res("prod"), Config(data={})) is None
    )  # no server


# ---- _require_context_server: explicit --context must resolve or fail loud ----
# Regression: `hop3 apps --context prod` used to silently fall back to the default
# (dev) server while accepting the flag. ADR 042: --context is the one selector
# for every command; it resolves project-then-global, or the command aborts.


def test_require_context_server_resolves_project():
    _write_toml(f'[metadata]\nid="a"\n[contexts.prod]\nserver="{ADDR}"\n')
    assert _require_context_server("prod", Config(data={})) == ADDR


def test_require_context_server_resolves_global_project_lessly():
    # The whole point: `hop3 apps --context prod` works with NO project present.
    cfg = Config(data={"contexts": {"prod": {"server": ADDR}}})
    assert _require_context_server("prod", cfg) == ADDR


def test_require_context_server_undefined_aborts(capsys):
    with pytest.raises(SystemExit) as exc:
        _require_context_server("prod", Config(data={}))
    assert exc.value.code == ExitCode.RESOLUTION_ERROR
    err = capsys.readouterr().err
    assert "not defined" in err  # says the name is unknown
    assert "hop3 context add" in err  # and how to define it


def test_require_context_server_lists_known_contexts(capsys):
    cfg = Config(data={"contexts": {"dev": {"server": "x"}}})
    with pytest.raises(SystemExit):
        _require_context_server("prod", cfg)
    assert "dev" in capsys.readouterr().err  # lists what IS defined


# ---- C1: explicit --context must not be silently overridden by an env URL ----
# `hop3 deploy --context prod` with HOP3_API_URL set used to connect to the env
# URL (get_api_url consults it first) while authenticating as prod — a
# wrong-target write. Now it aborts loud.


def test_env_url_shadowing_explicit_context_aborts(monkeypatch, capsys):
    monkeypatch.setenv("HOP3_API_URL", "ssh://root@other.example.com")
    with pytest.raises(SystemExit) as exc:
        _abort_if_env_url_shadows_context("prod", ADDR, Config(data={}))
    assert exc.value.code == ExitCode.RESOLUTION_ERROR
    err = capsys.readouterr().err
    assert "prod" in err
    assert "other.example.com" in err


def test_env_url_matching_context_does_not_abort(monkeypatch):
    # Same server (address forms differ only by the default ssh port) -> fine.
    monkeypatch.setenv("HOP3_API_URL", ADDR)
    _abort_if_env_url_shadows_context("prod", ADDR, Config(data={}))  # no raise


def test_no_env_url_does_not_abort(monkeypatch):
    monkeypatch.delenv("HOP3_API_URL", raising=False)
    monkeypatch.delenv("HOP3_DEV_MODE", raising=False)
    _abort_if_env_url_shadows_context("prod", ADDR, Config(data={}))  # no raise


# ---- C2: non-app-scoped auth commands resolve a context for server targeting --


def test_non_app_scoped_auth_command_resolves_context():
    # `hop3 apps` is not app-scoped but still targets a server, so the context
    # (HOP3_CONTEXT / .hop3-local.toml / sole project context) must be resolved.
    flags = SimpleNamespace(why=False, context=None, app=None)
    ctx_res, app_res = _compute_resolutions(["apps"], flags, Config(data={}))
    assert ctx_res is not None  # resolved for server targeting (C2)
    assert app_res is None  # but the command is not app-scoped


def test_no_auth_connecting_command_resolves_context():
    # Regression: `help` needs no token but still connects, so it must target
    # the same server as any other command. Gating resolution on "requires
    # authentication" sent `hop3 app logs --help` to the retired legacy
    # default_server while `hop3 app logs` reached the default context.
    flags = SimpleNamespace(why=False, context=None, app=None)
    ctx_res, app_res = _compute_resolutions(
        ["help", "app", "logs"], flags, Config(data={})
    )
    assert ctx_res is not None
    assert app_res is None


# ---- Config honors the active server ----


def test_active_server_drives_url_and_configured():
    cfg = Config(data={})
    assert cfg.get_api_url() is None
    cfg.set_active_server(ADDR)
    assert cfg.get_api_url() == ADDR
    assert cfg.is_configured() is True


def test_token_resolves_from_store_for_active_server():
    cfg = Config(data={})
    cfg.set_active_server(ADDR)
    assert cfg.get_api_token() is None  # store empty -> triggers bootstrap
    assert cfg.is_authenticated() is False
    cs.set_token(ADDR, "eyJtok")
    assert cfg.get_api_token() == "eyJtok"
    assert cfg.is_authenticated() is True


def test_update_context_token_routes_to_store_when_active():
    cfg = Config(data={})
    cfg.set_active_server(ADDR)
    cfg.update_context_token("bootstrapped")  # the SSH-bootstrap save path
    assert cs.get_token(ADDR) == "bootstrapped"
    # ...and equivalent address forms resolve the same key.
    assert cs.get_token(f"{ADDR}:22") == "bootstrapped"


def test_clearing_active_server_restores_legacy_path():
    cfg = Config(data={})
    cfg.set_active_server(ADDR)
    cfg.set_active_server(None)
    assert cfg.get_api_url() is None  # back to legacy (no context configured)


# ---- record_server_login (login/init populate store + default-server) ----


def test_record_server_login(tmp_path, capsys):
    cfg = Config(data={}, config_file=tmp_path / "config.toml")
    record_server_login(cfg, ADDR, "eyJtok")
    assert cs.get_token(ADDR) == "eyJtok"
    assert cfg.get_default_server() == ADDR
    assert "default server is now" in capsys.readouterr().out
    # Re-login to the same server doesn't re-announce the default.
    record_server_login(cfg, ADDR, "eyJtok2")
    assert "default server is now" not in capsys.readouterr().out
