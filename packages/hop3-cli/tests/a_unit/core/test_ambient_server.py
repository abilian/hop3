# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Ambient server selection for project-less commands with no --context (ADR 042).

`--context` is the explicit selector. With none given, the ambient chain is:
default context ([cli].default_context -> its server) -> legacy unnamed
default-server -> the sole token-store entry -> None (ambiguous/empty -> the
server-aware unconfigured message).
"""

from __future__ import annotations

from hop3_cli.config import Config
from hop3_cli.core import credential_store as cs
from hop3_cli.main import _resolve_ambient_server
from hop3_cli.ui.messages import show_unconfigured_message


def _cfg(tmp_path):
    return Config(data={}, config_file=tmp_path / "config.toml")


def test_default_context_wins(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.set_context_server("prod", "ssh://root@prod")
    cfg.set_default_context("prod")
    cfg.set_default_server("ssh://root@legacy")  # named default outranks the legacy one
    assert _resolve_ambient_server(cfg) == "ssh://root@prod"


def test_default_server_before_store(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.set_default_server("ssh://root@default")
    cs.set_token("ssh://root@a", "t")
    cs.set_token("ssh://root@b", "t")  # two in store, but default wins
    assert _resolve_ambient_server(cfg) == "ssh://root@default"


def test_sole_store_server(tmp_path):
    cfg = _cfg(tmp_path)
    cs.set_token("ssh://root@only", "t")
    assert _resolve_ambient_server(cfg) == cs.canonicalize("ssh://root@only")


def test_none_when_ambiguous(tmp_path):
    cfg = _cfg(tmp_path)
    cs.set_token("ssh://root@a", "t")
    cs.set_token("ssh://root@b", "t")
    assert _resolve_ambient_server(cfg) is None


def test_none_when_empty(tmp_path):
    assert _resolve_ambient_server(_cfg(tmp_path)) is None


def test_unconfigured_message_is_context_aware(capsys):
    cs.set_token("ssh://root@a", "t")
    cs.set_token("ssh://root@b", "t")
    show_unconfigured_message(["apps"])
    out = capsys.readouterr().out
    assert "ssh://root@a:22" in out
    assert "--context" in out  # guides to naming + selecting a context


def test_unconfigured_message_no_servers_shows_init(capsys):
    show_unconfigured_message(["apps"])
    assert "not configured" in capsys.readouterr().out.lower()
