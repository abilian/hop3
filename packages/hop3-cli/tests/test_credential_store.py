# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the per-server token store (ADR 042 r2, step C1).

The conftest autouse fixture points ``$HOP3_CONFIG_DIR`` at a per-test tmp dir,
so the store reads/writes there in isolation.
"""

from __future__ import annotations

import stat

import pytest
from hop3_cli.config import Config
from hop3_cli.core import credential_store as cs
from hop3_cli.core.paths import config_dir

# ---- canonicalize ----


def test_canonicalize_adds_default_ssh_port():
    assert cs.canonicalize("ssh://root@h.example.com") == "ssh://root@h.example.com:22"


def test_canonicalize_idempotent_and_port_equivalence():
    a = cs.canonicalize("ssh://root@h")
    b = cs.canonicalize("ssh://root@h:22")
    assert a == b == "ssh://root@h:22"


def test_canonicalize_https_default_port_and_lowercases_host():
    assert cs.canonicalize("https://Host.Example.COM") == "https://host.example.com:443"


def test_canonicalize_preserves_user_distinction():
    assert cs.canonicalize("ssh://deploy@h") != cs.canonicalize("ssh://root@h")


def test_canonicalize_non_url_returned_stripped():
    assert cs.canonicalize("  not-a-url  ") == "not-a-url"


# ---- get / set / known / remove ----


def test_set_get_roundtrip_by_equivalent_forms():
    cs.set_token("ssh://root@prod.example.com:22", "eyJtok")
    # Looked up by a different-but-equivalent address form.
    assert cs.get_token("ssh://root@prod.example.com") == "eyJtok"


def test_get_unknown_returns_none():
    assert cs.get_token("ssh://root@nope") is None


def test_known_servers_lists_canonical_addresses():
    cs.set_token("ssh://root@a", "t1")
    cs.set_token("https://b", "t2")
    assert cs.known_servers() == ["https://b:443", "ssh://root@a:22"]


def test_remove_token():
    cs.set_token("ssh://root@a", "t1")
    assert cs.remove_token("ssh://root@a:22") is True
    assert cs.get_token("ssh://root@a") is None
    assert cs.remove_token("ssh://root@a") is False


def test_set_token_overwrites():
    cs.set_token("ssh://root@a", "t1")
    cs.set_token("ssh://root@a:22", "t2")  # same canonical key
    assert cs.get_token("ssh://root@a") == "t2"
    assert cs.known_servers() == ["ssh://root@a:22"]


def test_store_file_is_private():
    cs.set_token("ssh://root@a", "t1")
    path = config_dir() / cs.CREDENTIALS_FILENAME
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & 0o077 == 0  # no group/world bits — tokens stay private


def test_missing_store_reads_empty():
    assert cs.known_servers() == []
    assert cs.get_token("ssh://root@a") is None


# ---- fail-loud abort paths (NON-NEGOTIABLE: never leave tokens readable) ----


def test_corrupt_store_aborts_loud():
    """A corrupt store must raise, not silently read as empty."""
    path = config_dir() / cs.CREDENTIALS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe not toml")
    with pytest.raises(cs.CredentialStoreError):
        cs.get_token("ssh://root@a")
    with pytest.raises(cs.CredentialStoreError):
        cs.known_servers()


def test_parent_dir_tightened_to_0700():
    cs.set_token("ssh://root@a", "t1")
    assert stat.S_IMODE(config_dir().stat().st_mode) == 0o700


def test_parent_dir_chmod_failure_aborts_loud(monkeypatch):
    """If the store dir can't be secured to 0o700, abort — don't write tokens."""

    def _boom(*_a, **_k):
        msg = "nope"
        raise OSError(msg)

    monkeypatch.setattr(cs.os, "chmod", _boom)
    with pytest.raises(cs.CredentialStoreError, match="0o700"):
        cs.set_token("ssh://root@a", "t1")


def test_group_world_readable_result_aborts_loud(monkeypatch):
    """If the written file ends up group/world-accessible, refuse loudly."""
    real_s_imode = stat.S_IMODE
    target = config_dir() / cs.CREDENTIALS_FILENAME

    def _leaky(mode):
        # Report a group-readable mode for the store file's stat only.
        return real_s_imode(mode) | 0o040

    monkeypatch.setattr(cs.stat, "S_IMODE", _leaky)
    with pytest.raises(cs.CredentialStoreError, match="group/world-accessible"):
        cs.set_token("ssh://root@a", "t1")
    # And the leaky write must not have left a readable token behind.
    monkeypatch.undo()
    assert not target.is_file() or stat.S_IMODE(target.stat().st_mode) & 0o077 == 0


# ---- Config default-server pointer ----


def test_default_server_roundtrip(tmp_path):
    cfg = Config(data={}, config_file=tmp_path / "config.toml")
    assert cfg.get_default_server() is None
    cfg.set_default_server("ssh://root@prod")
    assert cfg.get_default_server() == "ssh://root@prod"
    assert cfg.data["cli"]["default_server"] == "ssh://root@prod"
    cfg.set_default_server(None)
    assert cfg.get_default_server() is None
