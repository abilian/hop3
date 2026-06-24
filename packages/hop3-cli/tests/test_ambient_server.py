# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Ambient server selection for project-less commands (ADR 042 r2, step E2).

Chain: --server <addr> -> config.toml default-server -> sole token-store entry
-> None (ambiguous/empty -> the server-aware unconfigured message).
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3_cli.commands.flags import parse_flags
from hop3_cli.config import Config
from hop3_cli.core import credential_store as cs
from hop3_cli.main import _resolve_ambient_server
from hop3_cli.ui.messages import show_unconfigured_message


def _flags(server=None):
    return SimpleNamespace(server=server)


def _cfg(tmp_path):
    return Config(data={}, config_file=tmp_path / "config.toml")


def test_server_flag_wins(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.set_default_server("ssh://root@default")
    cs.set_token("ssh://root@store", "t")
    assert _resolve_ambient_server(_flags("ssh://root@flag"), cfg) == "ssh://root@flag"


def test_default_server_before_store(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.set_default_server("ssh://root@default")
    cs.set_token("ssh://root@a", "t")
    cs.set_token("ssh://root@b", "t")  # two in store, but default wins
    assert _resolve_ambient_server(_flags(), cfg) == "ssh://root@default"


def test_sole_store_server(tmp_path):
    cfg = _cfg(tmp_path)
    cs.set_token("ssh://root@only", "t")
    assert _resolve_ambient_server(_flags(), cfg) == cs.canonicalize("ssh://root@only")


def test_none_when_ambiguous(tmp_path):
    cfg = _cfg(tmp_path)
    cs.set_token("ssh://root@a", "t")
    cs.set_token("ssh://root@b", "t")
    assert _resolve_ambient_server(_flags(), cfg) is None


def test_none_when_empty(tmp_path):
    assert _resolve_ambient_server(_flags(), _cfg(tmp_path)) is None


def test_server_flag_parses():
    flags, rest = parse_flags(["apps", "--server", "ssh://root@h"])
    assert flags.server == "ssh://root@h"
    assert rest == ["apps"]


def test_unconfigured_message_is_server_aware(capsys):
    cs.set_token("ssh://root@a", "t")
    cs.set_token("ssh://root@b", "t")
    show_unconfigured_message(["apps"])
    out = capsys.readouterr().out
    assert "ssh://root@a:22" in out
    assert "--server" in out


def test_unconfigured_message_no_servers_shows_init(capsys):
    show_unconfigured_message(["apps"])
    assert "not configured" in capsys.readouterr().out.lower()
