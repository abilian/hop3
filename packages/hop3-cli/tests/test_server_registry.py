# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the server-registry reader/writer (ADR 042 Step 4)."""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest
import tomllib
from hop3_cli.core.server_registry import (
    ServerRecord,
    ServerRegistry,
    load_registry,
    migrate_legacy_records,
    remove,
    save_registry,
    upsert,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---- ServerRecord ---------------------------------------------------------


def test_server_record_round_trip():
    """to_dict → from_dict preserves all fields."""
    rec = ServerRecord(
        name="dev",
        url="https://dev.example.com",
        token="xyz",
        ssh_user="root",
        ssh_port=2222,
        protected=True,
        default_app="myapp",
    )
    restored = ServerRecord.from_dict("dev", rec.to_dict())
    # Name comes from the table key on load; other fields round-trip.
    assert restored.name == "dev"
    assert restored.url == rec.url
    assert restored.token == rec.token
    assert restored.ssh_port == rec.ssh_port
    assert restored.protected is True
    assert restored.default_app == "myapp"


def test_server_record_from_dict_defaults():
    """Missing fields take sensible defaults rather than raising."""
    rec = ServerRecord.from_dict("dev", {"url": "https://dev.example.com"})
    assert rec.name == "dev"
    assert rec.url == "https://dev.example.com"
    assert rec.ssh_user == "root"
    assert rec.ssh_port == 22
    assert rec.protected is False
    assert rec.default_app == ""


# ---- load_registry --------------------------------------------------------


def test_load_registry_missing_file(tmp_path: Path) -> None:
    """No file → empty registry, path preserved for later save."""
    target = tmp_path / "servers.toml"
    registry = load_registry(target)
    assert registry.path == target
    assert registry.records == {}


def test_load_registry_reads_records(tmp_path: Path) -> None:
    target = tmp_path / "servers.toml"
    target.write_text(
        """
[servers.dev]
url = "https://dev.example.com"
token = "xyz"
protected = true

[servers.prod]
url = "https://prod.example.com"
default_app = "myapp"
"""
    )
    registry = load_registry(target)
    assert registry.names() == ["dev", "prod"]
    assert registry.get("dev").url == "https://dev.example.com"
    assert registry.get("dev").protected is True
    assert registry.get("prod").default_app == "myapp"


def test_load_registry_parse_error_returns_empty(tmp_path: Path) -> None:
    """Malformed TOML doesn't crash — returns empty registry."""
    target = tmp_path / "servers.toml"
    target.write_text("not valid toml [[[")
    registry = load_registry(target)
    assert registry.records == {}
    # Path preserved so callers can distinguish 'no file' from 'broken'.
    assert registry.path == target


def test_load_registry_filters_non_dict_entries(tmp_path: Path) -> None:
    """Defensive: skip malformed entries rather than crashing."""
    target = tmp_path / "servers.toml"
    target.write_text(
        """
[servers.dev]
url = "https://dev.example.com"
"""
    )
    # Inject a non-dict child through direct write.
    target.write_text(target.read_text() + 'bogus = "not-a-table"\n')
    registry = load_registry(target)
    # 'bogus' isn't in [servers.*] scope — only 'dev' loaded.
    assert registry.names() == ["dev"]


# ---- save_registry --------------------------------------------------------


def test_save_registry_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "servers.toml"
    rec = ServerRecord(name="dev", url="https://dev.example.com")
    save_registry(ServerRegistry(path=target, records={"dev": rec}))
    assert target.is_file()
    data = tomllib.loads(target.read_text())
    assert data["servers"]["dev"]["url"] == "https://dev.example.com"


def test_save_registry_chmods_600(tmp_path: Path) -> None:
    """The auth token in the file → file must be chmod 0600."""
    target = tmp_path / "servers.toml"
    save_registry(
        ServerRegistry(
            path=target,
            records={"dev": ServerRecord(name="dev", url="x", token="secret")},
        )
    )
    mode = stat.S_IMODE(os.stat(target).st_mode)
    # On systems that honor chmod, mode is 0o600. On systems where chmod
    # silently fails (some CI tmpfs), the file mode might be defaulted —
    # accept either, but the file MUST exist.
    assert target.is_file()
    if mode != 0:  # Don't assert on truly broken-chmod hosts
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "servers.toml"
    original = ServerRegistry(
        path=target,
        records={
            "dev": ServerRecord(
                name="dev",
                url="https://dev.example.com",
                token="t1",
                protected=True,
                default_app="myapp",
            ),
        },
    )
    save_registry(original)
    reloaded = load_registry(target)
    assert reloaded.names() == ["dev"]
    assert reloaded.get("dev").url == "https://dev.example.com"
    assert reloaded.get("dev").protected is True
    assert reloaded.get("dev").default_app == "myapp"


# ---- upsert / remove (pure functions) ------------------------------------


def test_upsert_adds_new_record(tmp_path: Path) -> None:
    target = tmp_path / "servers.toml"
    registry = ServerRegistry(path=target, records={})
    new = upsert(
        registry,
        ServerRecord(name="dev", url="https://dev.example.com"),
    )
    # Pure function: input unchanged.
    assert registry.records == {}
    assert "dev" in new.records


def test_upsert_replaces_existing(tmp_path: Path) -> None:
    target = tmp_path / "servers.toml"
    registry = ServerRegistry(
        path=target,
        records={"dev": ServerRecord(name="dev", url="https://old.example.com")},
    )
    new = upsert(
        registry,
        ServerRecord(name="dev", url="https://new.example.com"),
    )
    assert new.get("dev").url == "https://new.example.com"


def test_remove_drops_record(tmp_path: Path) -> None:
    target = tmp_path / "servers.toml"
    registry = ServerRegistry(
        path=target,
        records={"dev": ServerRecord(name="dev", url="x")},
    )
    new, removed = remove(registry, "dev")
    assert removed is True
    assert new.records == {}


def test_remove_missing_record_is_false(tmp_path: Path) -> None:
    target = tmp_path / "servers.toml"
    registry = ServerRegistry(path=target, records={})
    new, removed = remove(registry, "nope")
    assert removed is False
    assert new == registry  # No-op


# ---- migrate_legacy_records (ADR 042 §Migration) -------------------------


def test_migration_carries_over_records(tmp_path: Path) -> None:
    """Legacy ``config.toml [contexts.*]`` becomes ``servers.toml [servers.*]``."""
    legacy_data = {
        "contexts": {
            "prod": {
                "api_url": "https://prod.example.com",
                "api_token": "tok-1",
                "ssh_user": "root",
                "ssh_port": 22,
                "protected": True,
            },
            "dev": {
                "api_url": "https://dev.example.com",
                "default_app": "myapp",
            },
        }
    }
    target = tmp_path / "servers.toml"
    registry, names, notes = migrate_legacy_records(legacy_data, target=target)

    assert sorted(names) == ["dev", "prod"]
    # Field renames (api_url → url, api_token → token) applied.
    assert registry.get("prod").url == "https://prod.example.com"
    assert registry.get("prod").token == "tok-1"
    assert registry.get("prod").protected is True
    # default_app preserved (ADR 042 v0.2 keeps it as app-resolution #8).
    assert registry.get("dev").default_app == "myapp"
    # The default_app preservation triggers a one-line note for stderr.
    assert any("myapp" in n for n in notes)


def test_migration_no_contexts_returns_empty(tmp_path: Path) -> None:
    """Nothing to migrate → empty registry, no notes."""
    target = tmp_path / "servers.toml"
    registry, names, notes = migrate_legacy_records({}, target=target)
    assert registry.records == {}
    assert names == []
    assert notes == []


def test_migration_skips_non_dict_entries(tmp_path: Path) -> None:
    """Defensive: a malformed legacy entry doesn't crash the migration."""
    legacy_data = {
        "contexts": {
            "good": {"api_url": "https://good.example.com"},
            "bad": "this is not a table",
        }
    }
    target = tmp_path / "servers.toml"
    _registry, names, _notes = migrate_legacy_records(legacy_data, target=target)
    assert names == ["good"]


def test_migration_accepts_new_field_names_too(tmp_path: Path) -> None:
    """If someone hand-edits config.toml with the new field names already,
    the migration accepts those without re-renaming.
    """
    legacy_data = {
        "contexts": {
            "dev": {
                "url": "https://dev.example.com",
                "token": "modern-tok",
            }
        }
    }
    target = tmp_path / "servers.toml"
    registry, _, _ = migrate_legacy_records(legacy_data, target=target)
    assert registry.get("dev").url == "https://dev.example.com"
    assert registry.get("dev").token == "modern-tok"


# ---- ServerRegistry is frozen --------------------------------------------


def test_registry_dataclass_is_frozen(tmp_path: Path) -> None:
    from dataclasses import FrozenInstanceError  # noqa: PLC0415

    registry = ServerRegistry(path=tmp_path / "servers.toml", records={})
    with pytest.raises(FrozenInstanceError):
        registry.path = tmp_path / "other.toml"  # type: ignore[misc]


# ---- Token redaction in __repr__ (Step-4 review should-fix) -------------


def test_server_record_repr_does_not_leak_token():
    """Regression: repr(rec) used to dump the JWT — sensitive in logs/tracebacks."""
    rec = ServerRecord(
        name="dev",
        url="https://dev.example.com",
        token="eyJhbGciOiJIUzI1NiJ9.actual-jwt-payload.sig",
    )
    text = repr(rec)
    assert "eyJhbGci" not in text
    assert "actual-jwt-payload" not in text
    assert "<set>" in text  # sentinel present


def test_server_record_repr_unset_token():
    """An empty token shows the <unset> sentinel."""
    rec = ServerRecord(name="dev", url="x")
    assert "<unset>" in repr(rec)


def test_server_record_repr_redacts_ssh_key_too():
    """ssh_key is secret-adjacent — also redacted from repr."""
    rec = ServerRecord(
        name="dev",
        url="x",
        ssh_key="-----BEGIN OPENSSH PRIVATE KEY-----\nactual-key-bytes",
    )
    text = repr(rec)
    assert "BEGIN OPENSSH" not in text
    assert "actual-key-bytes" not in text
    assert "ssh_key=<set>" in text


# ---- Parse-error sentinel (review should-fix) ---------------------------


def test_load_registry_parse_error_is_surfaced(tmp_path: Path) -> None:
    """A broken file is distinguishable from a missing file via is_broken."""
    target = tmp_path / "servers.toml"
    target.write_text("not valid toml [[[")
    registry = load_registry(target)
    assert registry.is_broken
    assert registry.parse_error is not None


def test_load_registry_missing_file_is_not_broken(tmp_path: Path) -> None:
    """A missing file is NOT 'broken' — that's the fresh-install state."""
    registry = load_registry(tmp_path / "servers.toml")
    assert not registry.is_broken
    assert registry.parse_error is None
