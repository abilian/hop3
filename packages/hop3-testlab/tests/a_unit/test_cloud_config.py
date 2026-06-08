# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Cloud config: file -> env -> default precedence, $ref resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_testlab.cloud_config import (
    DEFAULT_KEEP_RUNS,
    load_cloud_config,
    load_retention,
)

if TYPE_CHECKING:
    from pathlib import Path

_HZ = ("HETZNER_API_TOKEN", "HETZNER_SERVER_ID", "HOP3_TEST_SSH_KEY", "TESTLAB_CONFIG")


def _clear(monkeypatch):
    for var in _HZ:
        monkeypatch.delenv(var, raising=False)


def test_literals_from_toml_win(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[hetzner]\napi_token = "tok123"\nserver_id = 42\nimage = "debian-13"\n'
        '[ssh]\nkey_path = "/keys/id_ed25519"\n'
    )
    cfg = load_cloud_config(cfg_file)
    assert cfg.hetzner_token == "tok123"
    assert cfg.hetzner_server_id == 42
    assert cfg.hetzner_image == "debian-13"
    assert cfg.ssh_key_path == "/keys/id_ed25519"
    assert cfg.is_complete


def test_env_refs_in_toml_resolve(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HETZNER_API_TOKEN", "envtok")
    monkeypatch.setenv("HETZNER_SERVER_ID", "99")
    monkeypatch.setenv("HOP3_TEST_SSH_KEY", "/env/key")
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[hetzner]\napi_token = "$HETZNER_API_TOKEN"\nserver_id = "$HETZNER_SERVER_ID"\n'
        '[ssh]\nkey_path = "$HOP3_TEST_SSH_KEY"\n'
    )
    cfg = load_cloud_config(cfg_file)
    assert cfg.hetzner_token == "envtok"
    assert cfg.hetzner_server_id == 99
    assert cfg.ssh_key_path == "/env/key"


def test_env_fallback_when_no_file(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HETZNER_API_TOKEN", "etok")
    monkeypatch.setenv("HETZNER_SERVER_ID", "7")
    # An explicit, non-existent path skips discovery -> pure env.
    cfg = load_cloud_config(tmp_path / "nope.toml")
    assert cfg.hetzner_token == "etok"
    assert cfg.hetzner_server_id == 7
    assert cfg.is_complete


def test_incomplete_when_nothing_set(tmp_path: Path, monkeypatch):
    _clear(monkeypatch)
    cfg = load_cloud_config(tmp_path / "nope.toml")
    assert not cfg.is_complete


def test_retention_from_toml(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TESTLAB_LOG_RETENTION_RUNS", raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[retention]\nkeep_runs = 7\n")
    assert load_retention(cfg_file) == 7


def test_retention_env_fallback_then_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TESTLAB_LOG_RETENTION_RUNS", "5")
    assert load_retention(tmp_path / "nope.toml") == 5
    monkeypatch.delenv("TESTLAB_LOG_RETENTION_RUNS", raising=False)
    assert load_retention(tmp_path / "nope.toml") == DEFAULT_KEEP_RUNS
