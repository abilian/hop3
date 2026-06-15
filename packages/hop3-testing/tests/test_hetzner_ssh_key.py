# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Resolving the SSH key Hetzner re-injects on rebuild (explicit or auto-derived).

A rebuild with no key locks us out, so an unresolvable key is a hard, explained
error — never a silent skip. The key is taken from hetzner.ssh_key_name, or
auto-derived from [ssh] key_path by matching <path>.pub's fingerprint against the
project's registered keys.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from hop3_testing.system_tests.config import HetznerConfig
from hop3_testing.system_tests.hetzner import (
    HetznerManager,
    ServerResetError,
    _public_key_md5_fingerprint,
)


def _manager(ssh_key_name=None, ssh_key_path=None) -> HetznerManager:
    m = HetznerManager(
        HetznerConfig(
            api_token="t",
            server_id=1,
            image="ubuntu-24.04",
            ssh_key_name=ssh_key_name,
            ssh_key_path=ssh_key_path,
        )
    )
    m._client = MagicMock()
    return m


def _write_pubkey(tmp_path) -> str:
    """Write a parseable .pub; return the key path (without the .pub suffix)."""
    (tmp_path / "id.pub").write_text("ssh-rsa AAAAB3NzaC1yc2E= test\n")
    return str(tmp_path / "id")


# --- fingerprint ----------------------------------------------------------


def test_fingerprint_is_md5_colon_hex(tmp_path):
    fp = _public_key_md5_fingerprint(_write_pubkey(tmp_path))
    assert fp is not None
    assert len(fp.split(":")) == 16  # MD5 digest = 16 bytes


def test_fingerprint_none_when_pub_missing(tmp_path):
    assert _public_key_md5_fingerprint(str(tmp_path / "nope")) is None


# --- explicit ssh_key_name ------------------------------------------------


def test_explicit_name_found_is_used():
    m = _manager(ssh_key_name="mine")
    key = SimpleNamespace(name="mine", fingerprint="x")
    m._client.ssh_keys.get_by_name.return_value = key
    assert m.resolve_ssh_key() is key


def test_explicit_name_not_found_raises_loudly():
    m = _manager(ssh_key_name="ghost")
    m._client.ssh_keys.get_by_name.return_value = None
    with pytest.raises(ServerResetError, match="not a key registered"):
        m.resolve_ssh_key()


# --- auto-derive from key_path -------------------------------------------


def test_autoderive_matches_registered_key(tmp_path):
    key_path = _write_pubkey(tmp_path)
    fp = _public_key_md5_fingerprint(key_path)
    m = _manager(ssh_key_path=key_path)
    m._client.ssh_keys.get_all.return_value = [
        SimpleNamespace(name="other", fingerprint="00:11"),
        SimpleNamespace(name="mine", fingerprint=fp),
    ]
    assert m.resolve_ssh_key().name == "mine"


def test_autoderive_no_match_raises_loudly(tmp_path):
    m = _manager(ssh_key_path=_write_pubkey(tmp_path))
    m._client.ssh_keys.get_all.return_value = [
        SimpleNamespace(name="other", fingerprint="00:11"),
    ]
    with pytest.raises(ServerResetError, match=r"not.*registered"):
        m.resolve_ssh_key()


def test_no_name_no_keypath_raises_loudly():
    with pytest.raises(ServerResetError, match="neither"):
        _manager().resolve_ssh_key()
