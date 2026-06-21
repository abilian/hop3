# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""start_run records run provenance (trigger / git_sha) — ADR 044 §D."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3_testing.results import ResultStore

if TYPE_CHECKING:
    from pathlib import Path


def test_start_run_records_explicit_provenance(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HOP3_TEST_TRIGGER", raising=False)
    store = ResultStore(db_path=tmp_path / "r.db")
    run = store.start_run(
        mode="nightly",
        target_type="hetzner",
        target_name="hop3-dev",
        trigger="scheduled-nightly",
        git_sha="abc123",
    )
    assert run.trigger == "scheduled-nightly"
    assert run.git_sha == "abc123"


def test_start_run_trigger_defaults_to_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOP3_TEST_TRIGGER", "web:alice")
    store = ResultStore(db_path=tmp_path / "r2.db")
    run = store.start_run(mode="cli", target_type="docker", target_name="t")
    assert run.trigger == "web:alice"


def test_start_run_trigger_falls_back_to_cli(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HOP3_TEST_TRIGGER", raising=False)
    store = ResultStore(db_path=tmp_path / "r3.db")
    run = store.start_run(mode="cli", target_type="docker", target_name="t")
    assert run.trigger == "cli"


def test_start_run_merges_metadata_param_and_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOP3_TEST_META", '{"os_name": "ubuntu", "server_type": "cx43"}')
    store = ResultStore(db_path=tmp_path / "m.db")
    run = store.start_run(
        mode="nightly",
        target_type="ssh",
        target_name="hop3-dev",
        metadata={"region": "eu"},
    )
    meta = run.run_metadata
    assert meta is not None
    assert meta["os_name"] == "ubuntu"  # from $HOP3_TEST_META
    assert meta["server_type"] == "cx43"  # from env
    assert meta["region"] == "eu"  # from the param


def test_start_run_rejects_malformed_meta(tmp_path: Path, monkeypatch):
    """A malformed HOP3_TEST_META fails loud — never silently drops provenance."""
    monkeypatch.setenv("HOP3_TEST_META", "not-json{")
    store = ResultStore(db_path=tmp_path / "bad.db")
    with pytest.raises(ValueError, match="HOP3_TEST_META"):
        store.start_run(mode="cli", target_type="docker", target_name="t")


def test_start_run_autodetects_hop3_version(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HOP3_TEST_META", raising=False)
    store = ResultStore(db_path=tmp_path / "v.db")
    run = store.start_run(mode="cli", target_type="docker", target_name="t")
    # hop3-server is installed in the dev/test env, so the version is captured.
    assert run.hop3_version
