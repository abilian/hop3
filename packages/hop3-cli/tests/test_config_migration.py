# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the one-shot ADR-042 config migration (config_migration.py).

Every test drives ``migrate_legacy_config_042`` against an isolated tmp config
dir, so nothing here can touch the developer's real ~/.config.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import toml
import tomllib
from hop3_cli.core.config_migration import MigrationError, migrate_legacy_config_042

if TYPE_CHECKING:
    from pathlib import Path


def _write(path: Path, data: dict) -> None:
    path.write_text(toml.dumps(data), encoding="utf-8")


def _read(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# No-op fast path (zero writes)
# --------------------------------------------------------------------------- #
def test_fresh_empty_dir_is_noop(tmp_path: Path) -> None:
    assert migrate_legacy_config_042(tmp_path) == []
    assert list(tmp_path.iterdir()) == []  # nothing created


def test_already_migrated_is_noop_zero_writes(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    _write(
        cfg,
        {
            "contexts": {
                "prod": {
                    "url": "https://p",
                    "token": "t",
                    "api_url": "https://p",
                    "api_token": "t",
                }
            },
            "cli": {"current_context": "prod"},
            "current_context": "prod",
        },
    )
    before = cfg.read_bytes()
    assert migrate_legacy_config_042(tmp_path) == []
    assert cfg.read_bytes() == before  # byte-for-byte unchanged
    assert not (tmp_path / "config.toml.pre-042r.bak").exists()


# --------------------------------------------------------------------------- #
# (a) legacy config.toml only
# --------------------------------------------------------------------------- #
def test_legacy_config_only(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        {
            "current_context": "prod",
            "theme": "dark",  # unrelated preference must survive
            "contexts": {
                "prod": {
                    "api_url": "https://prod",
                    "api_token": "T",
                    "protected": True,
                    "default_app": "old",
                }
            },
        },
    )
    notes = migrate_legacy_config_042(tmp_path)

    cfg = _read(tmp_path / "config.toml")
    ctx = cfg["contexts"]["prod"]
    assert ctx["url"] == "https://prod"
    assert ctx["token"] == "T"
    assert ctx["protected"] is True
    assert "default_app" not in ctx  # dropped
    assert ctx["api_url"] == "https://prod"  # downgrade mirror
    assert ctx["api_token"] == "T"
    assert cfg["cli"]["current_context"] == "prod"
    assert cfg["current_context"] == "prod"  # top-level mirror (current reader)
    assert cfg["theme"] == "dark"
    # original preserved in the backup
    assert (
        _read(tmp_path / "config.toml.pre-042r.bak")["contexts"]["prod"]["api_url"]
        == "https://prod"
    )
    assert any("default_app" in n for n in notes)


# --------------------------------------------------------------------------- #
# (b) servers.toml only
# --------------------------------------------------------------------------- #
def test_servers_only(tmp_path: Path) -> None:
    _write(
        tmp_path / "servers.toml",
        {"servers": {"dev": {"url": "https://dev", "token": "D", "default_app": "x"}}},
    )
    _write(tmp_path / "state.toml", {"current_server": "dev"})

    migrate_legacy_config_042(tmp_path)

    cfg = _read(tmp_path / "config.toml")
    assert cfg["contexts"]["dev"]["url"] == "https://dev"
    assert "default_app" not in cfg["contexts"]["dev"]
    assert cfg["cli"]["current_context"] == "dev"
    assert not (tmp_path / "servers.toml").exists()  # deleted last
    assert not (tmp_path / "state.toml").exists()  # was pointer-only -> removed
    assert (tmp_path / "servers.toml.pre-042r.bak").exists()
    assert (tmp_path / "state.toml.pre-042r.bak").exists()


# --------------------------------------------------------------------------- #
# (c) all sources + same-name collision (token-bearing record wins)
# --------------------------------------------------------------------------- #
def test_collision_prefers_token_bearing_record(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        {"contexts": {"prod": {"api_url": "https://old", "api_token": ""}}},
    )
    _write(
        tmp_path / "servers.toml",
        {"servers": {"prod": {"url": "https://new", "token": "TK"}}},
    )
    migrate_legacy_config_042(tmp_path)

    ctx = _read(tmp_path / "config.toml")["contexts"]["prod"]
    assert ctx["url"] == "https://new"
    assert ctx["token"] == "TK"


# --------------------------------------------------------------------------- #
# (d) shape 3: config.toml gone (-> .pre-042.bak), servers.toml present
# --------------------------------------------------------------------------- #
def test_shape3_reads_old_lazy_backup(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml.pre-042.bak",
        {
            "current_context": "prod",
            "theme": "light",
            "contexts": {"prod": {"api_url": "https://p", "api_token": "T"}},
        },
    )
    _write(
        tmp_path / "servers.toml",
        {"servers": {"dev": {"url": "https://d", "token": "D"}}},
    )

    migrate_legacy_config_042(tmp_path)

    cfg = _read(tmp_path / "config.toml")
    assert set(cfg["contexts"]) == {"prod", "dev"}
    assert cfg["theme"] == "light"  # preferences recovered from the old backup
    assert cfg["cli"]["current_context"] == "prod"
    assert not (tmp_path / "servers.toml").exists()


# --------------------------------------------------------------------------- #
# (f) pointer conflict — current_server wins over legacy current_context
# --------------------------------------------------------------------------- #
def test_pointer_conflict_current_server_wins(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        {
            "current_context": "staging",
            "contexts": {
                "staging": {"api_url": "https://s"},
                "prod": {"api_url": "https://p"},
            },
        },
    )
    _write(tmp_path / "state.toml", {"current_server": "prod"})

    migrate_legacy_config_042(tmp_path)

    cfg = _read(tmp_path / "config.toml")
    assert cfg["cli"]["current_context"] == "prod"
    assert cfg["current_context"] == "prod"


# --------------------------------------------------------------------------- #
# (g) dangling pointer — abort loud, change nothing
# --------------------------------------------------------------------------- #
def test_dangling_pointer_aborts_unchanged(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    _write(cfg, {"contexts": {"prod": {"api_url": "https://p"}}})
    _write(tmp_path / "state.toml", {"current_server": "ghost"})
    before = cfg.read_bytes()

    with pytest.raises(MigrationError, match="ghost"):
        migrate_legacy_config_042(tmp_path)

    assert cfg.read_bytes() == before
    assert not (tmp_path / "config.toml.pre-042r.bak").exists()  # never reached backups


# --------------------------------------------------------------------------- #
# (h) malformed config.toml — abort, change nothing
# --------------------------------------------------------------------------- #
def test_malformed_config_aborts_unchanged(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("this is = = not [[[ toml", encoding="utf-8")

    with pytest.raises(MigrationError, match="malformed"):
        migrate_legacy_config_042(tmp_path)

    assert "not [[[ toml" in cfg.read_text()  # untouched
    assert not (tmp_path / "config.toml.pre-042r.bak").exists()


# --------------------------------------------------------------------------- #
# (i) malformed servers.toml — abort, refuse to delete it
# --------------------------------------------------------------------------- #
def test_malformed_servers_aborts_and_keeps_file(tmp_path: Path) -> None:
    _write(tmp_path / "config.toml", {"contexts": {"prod": {"api_url": "https://p"}}})
    srv = tmp_path / "servers.toml"
    srv.write_text("[[[ broken", encoding="utf-8")

    with pytest.raises(MigrationError, match="malformed"):
        migrate_legacy_config_042(tmp_path)

    assert srv.exists()  # not deleted


# --------------------------------------------------------------------------- #
# (j) crash-window resumability — re-run converges
# --------------------------------------------------------------------------- #
def test_resume_after_config_written_before_servers_deleted(tmp_path: Path) -> None:
    # Simulate a crash between "config.toml written" and "servers.toml deleted".
    _write(
        tmp_path / "config.toml",
        {
            "contexts": {
                "prod": {
                    "url": "https://p",
                    "token": "T",
                    "api_url": "https://p",
                    "api_token": "T",
                }
            },
            "cli": {"current_context": "prod"},
            "current_context": "prod",
        },
    )
    _write(
        tmp_path / "servers.toml",
        {"servers": {"prod": {"url": "https://p", "token": "T"}}},
    )

    migrate_legacy_config_042(tmp_path)

    assert not (tmp_path / "servers.toml").exists()
    assert _read(tmp_path / "config.toml")["contexts"]["prod"]["url"] == "https://p"


# --------------------------------------------------------------------------- #
# (k) backup non-clobber — a second pass keeps the TRUE original backup
# --------------------------------------------------------------------------- #
def test_backup_not_clobbered_on_rerun(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    _write(cfg, {"contexts": {"prod": {"api_url": "https://orig", "api_token": "T"}}})
    original = cfg.read_bytes()

    migrate_legacy_config_042(tmp_path)
    bak = tmp_path / "config.toml.pre-042r.bak"
    assert bak.read_bytes() == original

    # Force a second migrating pass by re-introducing a servers.toml.
    _write(
        tmp_path / "servers.toml",
        {"servers": {"dev": {"url": "https://d", "token": "D"}}},
    )
    migrate_legacy_config_042(tmp_path)

    assert (
        bak.read_bytes() == original
    )  # still the TRUE original, not a half-mutated file
    assert set(_read(cfg)["contexts"]) == {"prod", "dev"}


# --------------------------------------------------------------------------- #
# (l) downgrade mirror — both key spellings present
# --------------------------------------------------------------------------- #
def test_downgrade_mirror_present(tmp_path: Path) -> None:
    _write(
        tmp_path / "config.toml",
        {"contexts": {"prod": {"api_url": "https://p", "api_token": "T"}}},
    )
    migrate_legacy_config_042(tmp_path)

    ctx = _read(tmp_path / "config.toml")["contexts"]["prod"]
    assert ctx["url"] == ctx["api_url"] == "https://p"
    assert ctx["token"] == ctx["api_token"] == "T"
