# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the addon secrets store.

The store holds plaintext credentials (see the module docstring and
security-model.md §3.4.7), so the file mode is the whole protection and the
write must never widen it, not even briefly.
"""

from __future__ import annotations

import json
import os
import stat
from typing import TYPE_CHECKING

import pytest

from hop3.plugins.addons import secrets as secrets_mod
from hop3.plugins.addons.secrets import (
    delete_addon_secrets,
    list_addon_instances,
    load_addon_secrets,
    save_addon_secrets,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_hop3_root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(secrets_mod, "HOP3_ROOT", tmp_path)
    return tmp_path


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_saved_secrets_round_trip(tmp_hop3_root):
    save_addon_secrets("postgresql", "my-db", {"password": "s3cret"})

    assert load_addon_secrets("postgresql", "my-db") == {"password": "s3cret"}


def test_secrets_file_is_owner_only(tmp_hop3_root):
    save_addon_secrets("postgresql", "my-db", {"password": "s3cret"})

    path = tmp_hop3_root / "addons" / "postgresql" / "my-db.json"
    assert _mode(path) == 0o600


def test_secrets_file_is_owner_only_regardless_of_umask(tmp_hop3_root, monkeypatch):
    """
    The old writer created the file at 0644 under the default umask and only
    then chmod'ed it, publishing the password for the length of the write.
    mkstemp is umask-independent, so a permissive umask cannot widen it.
    """
    old = os.umask(0o000)
    try:
        save_addon_secrets("mysql", "loose", {"password": "s3cret"})
    finally:
        os.umask(old)

    assert _mode(tmp_hop3_root / "addons" / "mysql" / "loose.json") == 0o600


def test_rotation_tightens_a_pre_existing_loose_file(tmp_hop3_root):
    """A file left 0644 by an older release is fixed by the next write."""
    path = tmp_hop3_root / "addons" / "redis" / "legacy.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"password": "old"}))
    path.chmod(0o644)

    save_addon_secrets("redis", "legacy", {"password": "new"})

    assert _mode(path) == 0o600
    assert load_addon_secrets("redis", "legacy") == {"password": "new"}


def test_a_failed_write_keeps_the_previous_credential(tmp_hop3_root):
    """
    Truncate-then-write destroyed the live credential before producing its
    replacement, so a serialisation failure lost a password that still had a
    database behind it. The write is atomic now.
    """
    save_addon_secrets("postgresql", "keeper", {"password": "still-valid"})

    with pytest.raises(TypeError):
        save_addon_secrets("postgresql", "keeper", {"password": object()})

    assert load_addon_secrets("postgresql", "keeper") == {"password": "still-valid"}


def test_a_failed_write_leaves_no_temp_file_behind(tmp_hop3_root):
    """The temp file holds the same plaintext; a failure must not strand it."""
    with pytest.raises(TypeError):
        save_addon_secrets("postgresql", "doomed", {"password": object()})

    secrets_dir = tmp_hop3_root / "addons" / "postgresql"
    assert list(secrets_dir.iterdir()) == []


def test_missing_secrets_load_as_none(tmp_hop3_root):
    assert load_addon_secrets("postgresql", "never-created") is None


def test_delete_removes_the_file(tmp_hop3_root):
    save_addon_secrets("postgresql", "short-lived", {"password": "x"})

    delete_addon_secrets("postgresql", "short-lived")

    assert load_addon_secrets("postgresql", "short-lived") is None


def test_list_instances_ignores_the_writers_temp_files(tmp_hop3_root):
    """The registry globs *.json; a stray temp file must not read as an addon."""
    save_addon_secrets("postgresql", "real", {"password": "x"})
    (tmp_hop3_root / "addons" / "postgresql" / ".real.abc.tmp").write_text("{}")

    assert list_addon_instances() == [("postgresql", "real")]
