# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for Wave 4 backup-dir permission hardening.

Backup files contain plaintext env.json and DB dumps (at-rest encryption
deferred to 0.6 per ADR 024). Until then, the entire tree rooted at
BACKUP_ROOT must be 0o700 so one compromised app running as the shared
hop3 user cannot read another app's dumps.
"""

from __future__ import annotations

import stat
from pathlib import Path  # ruff:ignore[typing-only-standard-library-import]

import pytest

from hop3.config import HopConfig
from hop3.core.backup import _chmod_if_looser, _ensure_secure_backup_dir


@pytest.fixture
def patched_backup_root(tmp_path: Path, monkeypatch) -> Path:
    """Point HopConfig.BACKUP_ROOT at a temp dir for this test."""
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    # Loosen the test dir so we can observe the tightening effect.
    backup_root.chmod(0o755)

    cfg = HopConfig.get_instance()
    monkeypatch.setattr(
        type(cfg),
        "BACKUP_ROOT",
        property(lambda self: backup_root),
    )
    return backup_root


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_ensure_secure_backup_dir_tightens_leaf(patched_backup_root: Path) -> None:
    leaf = patched_backup_root / "apps" / "myapp" / "20260424_121314_abc123"
    _ensure_secure_backup_dir(leaf)
    assert leaf.exists()
    assert _mode(leaf) == 0o700


def test_ensure_secure_backup_dir_tightens_whole_chain(
    patched_backup_root: Path,
) -> None:
    """
    Ancestors created by parents=True also have to become 0o700,
    otherwise a traversal-via-apps reveals app directory listings.
    """
    leaf = patched_backup_root / "apps" / "myapp" / "20260424_121314_abc123"
    _ensure_secure_backup_dir(leaf)
    # Every level between BACKUP_ROOT and the leaf is now 0o700.
    assert _mode(patched_backup_root / "apps") == 0o700
    assert _mode(patched_backup_root / "apps" / "myapp") == 0o700
    assert _mode(patched_backup_root) == 0o700


def test_ensure_secure_backup_dir_idempotent(patched_backup_root: Path) -> None:
    leaf = patched_backup_root / "apps" / "myapp" / "20260424_121314_abc123"
    _ensure_secure_backup_dir(leaf)
    _ensure_secure_backup_dir(leaf)  # second call must not raise
    assert _mode(leaf) == 0o700


def test_ensure_secure_backup_dir_skips_tightening_outside_backup_root(
    tmp_path: Path, patched_backup_root: Path
) -> None:
    """
    If called on a path not under BACKUP_ROOT (test shim) we still
    tighten the leaf but do not traipse up.
    """
    stray = tmp_path / "stray" / "deeper"
    _ensure_secure_backup_dir(stray)
    assert _mode(stray) == 0o700
    # The parent was created by mkdir(parents=True) and is NOT tightened
    # because we bailed out of the walk; that's acceptable because the
    # stray path is outside our jurisdiction.


def test_chmod_if_looser_no_op_on_already_tight(patched_backup_root: Path) -> None:
    target = patched_backup_root / "tight"
    target.mkdir(mode=0o700)
    assert _mode(target) == 0o700
    _chmod_if_looser(target, 0o700)
    assert _mode(target) == 0o700


def test_chmod_if_looser_tightens_looser_modes(patched_backup_root: Path) -> None:
    target = patched_backup_root / "loose"
    target.mkdir(mode=0o755)
    _chmod_if_looser(target, 0o700)
    assert _mode(target) == 0o700


def test_chmod_if_looser_tolerates_missing_path(patched_backup_root: Path) -> None:
    target = patched_backup_root / "does_not_exist"
    # Must not raise.
    _chmod_if_looser(target, 0o700)
