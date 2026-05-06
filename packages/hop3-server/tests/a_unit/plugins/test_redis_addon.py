# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for RedisAddon db_number allocation and persistence."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_hop3_root(tmp_path, monkeypatch) -> Path:
    """Redirect HOP3_ROOT to a temporary directory for the duration of one test.

    HOP3_ROOT is imported into several modules at import time, so we monkeypatch
    each consumer that reads it.
    """
    from hop3.plugins.addons import secrets as secrets_mod  # noqa: PLC0415
    from hop3.plugins.redis import redis as redis_mod  # noqa: PLC0415

    monkeypatch.setattr(redis_mod, "HOP3_ROOT", tmp_path)
    monkeypatch.setattr(secrets_mod, "HOP3_ROOT", tmp_path)
    return tmp_path


def _write_secrets(root: Path, addon_name: str, db_number: int) -> None:
    secrets_dir = root / "addons" / "redis"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / f"{addon_name}.json").write_text(
        json.dumps({"db_number": db_number, "created_at": "2026-05-06T00:00:00+00:00"})
    )


def test_redis_addon_requires_addon_name():
    from hop3.plugins.redis.redis import RedisAddon  # noqa: PLC0415

    with pytest.raises(ValueError, match="addon_name is required"):
        RedisAddon(addon_name="")


def test_redis_addon_rejects_unsafe_addon_name(tmp_hop3_root):
    from hop3.core.identifiers import InvalidIdentifierError  # noqa: PLC0415
    from hop3.plugins.redis.redis import RedisAddon  # noqa: PLC0415

    with pytest.raises(InvalidIdentifierError):
        RedisAddon(addon_name="bad name with spaces")


def test_redis_addon_loads_persisted_db_number(tmp_hop3_root):
    from hop3.plugins.redis.redis import RedisAddon  # noqa: PLC0415

    _write_secrets(tmp_hop3_root, "my-cache", 7)

    addon = RedisAddon(addon_name="my-cache")
    assert addon.db_number == 7


def test_redis_addon_db_number_unset_until_create(tmp_hop3_root):
    """A fresh addon has no db assigned until create() runs."""
    from hop3.plugins.redis.redis import RedisAddon  # noqa: PLC0415

    addon = RedisAddon(addon_name="new-cache")
    # 0 is the sentinel for "not assigned" — db 0 is reserved.
    assert addon.db_number == 0


def test_allocate_db_number_starts_at_one(tmp_hop3_root):
    from hop3.plugins.redis.redis import _allocate_db_number  # noqa: PLC0415

    assert _allocate_db_number() == 1


def test_allocate_db_number_skips_used(tmp_hop3_root):
    from hop3.plugins.redis.redis import _allocate_db_number  # noqa: PLC0415

    _write_secrets(tmp_hop3_root, "addon-a", 1)
    _write_secrets(tmp_hop3_root, "addon-b", 2)
    _write_secrets(tmp_hop3_root, "addon-c", 4)

    # Should pick the lowest free number, which is 3.
    assert _allocate_db_number() == 3


def test_allocate_db_number_raises_when_full(tmp_hop3_root):
    from hop3.plugins.redis.redis import _allocate_db_number  # noqa: PLC0415

    for n in range(1, 16):
        _write_secrets(tmp_hop3_root, f"addon-{n}", n)

    with pytest.raises(RuntimeError, match="All Redis databases"):
        _allocate_db_number()


def test_allocate_db_number_ignores_corrupt_secrets(tmp_hop3_root):
    """A corrupt secrets file shouldn't block allocation."""
    from hop3.plugins.redis.redis import _allocate_db_number  # noqa: PLC0415

    secrets_dir = tmp_hop3_root / "addons" / "redis"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "broken.json").write_text("not json")
    (secrets_dir / "no-db-number.json").write_text(json.dumps({"created_at": "x"}))

    assert _allocate_db_number() == 1


def test_redis_addon_assignment_is_deterministic_after_persist(tmp_hop3_root):
    """Two different addons get distinct numbers; same addon keeps its number."""
    from hop3.plugins.redis.redis import RedisAddon  # noqa: PLC0415

    _write_secrets(tmp_hop3_root, "first", 1)
    _write_secrets(tmp_hop3_root, "second", 2)

    a = RedisAddon(addon_name="first")
    b = RedisAddon(addon_name="second")
    assert a.db_number == 1
    assert b.db_number == 2
    # Same name, same number — even if PYTHONHASHSEED changes between calls
    # (which it does between processes by default).
    a2 = RedisAddon(addon_name="first")
    assert a2.db_number == 1
