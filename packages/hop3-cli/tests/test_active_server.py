# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the v2 connection path (ADR 042 r2, step C2).

When a context resolves to a `[contexts.<name>].server` in the project hop3.toml,
that address becomes `config._active_server`, and the connection (url + token)
flows from it + the per-server token store — not the legacy config.toml context.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from hop3_cli.commands.local.login_cmd import record_server_login
from hop3_cli.config import Config
from hop3_cli.core import credential_store as cs
from hop3_cli.main import _resolve_active_server

ADDR = "ssh://root@prod.example.com"


def _ctx_res(context: str | None) -> SimpleNamespace:
    return SimpleNamespace(context=context)


def _write_toml(text: str) -> None:
    (Path.cwd() / "hop3.toml").write_text(text)


# ---- _resolve_active_server (context name -> hop3.toml server) ----


def test_resolve_active_server_from_hop3_toml():
    _write_toml(f'[metadata]\nid="a"\n[contexts.prod]\nserver="{ADDR}"\n')
    assert _resolve_active_server(_ctx_res("prod")) == ADDR


def test_resolve_active_server_none_when_no_context():
    assert _resolve_active_server(None) is None
    assert _resolve_active_server(_ctx_res(None)) is None


def test_resolve_active_server_unknown_or_serverless():
    _write_toml('[metadata]\nid="a"\n[contexts.prod]\nserver="x"\n')
    assert _resolve_active_server(_ctx_res("dev")) is None  # not declared
    _write_toml('[metadata]\nid="a"\n[contexts.prod]\napp="a"\n')
    assert _resolve_active_server(_ctx_res("prod")) is None  # no server field


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
