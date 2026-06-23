# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""ResultStore migration + bundle-pointer round-trip (ADR 043 Phase 1).

A pre-existing ~/.hop3/test-results.db created before the bundle columns must
keep working: ResultStore._ensure_columns adds the missing columns rather than
throwing ``no such column`` on the first query.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import ClassVar

import pytest
from hop3_testing.bundle import Bundle
from hop3_testing.results import ResultStore
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

# Old schema: the columns that existed BEFORE Phase 1 (no run_uid / bundle_*).
_OLD_RUNS = """
CREATE TABLE test_runs (
    id INTEGER PRIMARY KEY,
    started_at DATETIME, finished_at DATETIME,
    mode VARCHAR(20), target_type VARCHAR(20), target_name VARCHAR(100),
    hop3_version VARCHAR(50),
    total_tests INTEGER, passed_tests INTEGER, failed_tests INTEGER
)
"""
_OLD_RESULTS = """
CREATE TABLE test_results (
    id INTEGER PRIMARY KEY,
    run_id INTEGER,
    test_name VARCHAR(100), category VARCHAR(20), tier VARCHAR(20),
    priority VARCHAR(5), passed BOOLEAN, duration FLOAT,
    error TEXT, logs TEXT, executed_at DATETIME
)
"""


def _make_old_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(_OLD_RUNS)
    conn.execute(_OLD_RESULTS)
    conn.execute(
        "INSERT INTO test_runs (mode, target_type, target_name) "
        "VALUES ('nightly', 'docker', 'legacy-row')"
    )
    conn.commit()
    conn.close()


def test_ensure_columns_migrates_old_db(tmp_path: Path) -> None:
    db = tmp_path / "test-results.db"
    _make_old_db(db)

    # Opening the store must ALTER the old tables, not crash.
    store = ResultStore(db_path=db)

    cols_runs = {
        r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(test_runs)")
    }
    cols_results = {
        r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(test_results)")
    }
    assert "run_uid" in cols_runs
    assert {
        "bundle_run_id",
        "bundle_path",
        "classification",
        "headline",
    } <= cols_results

    # The pre-existing NULL-run_uid row coexists with the partial unique index.
    run = store.start_run(mode="nightly", target_type="docker", target_name="t")
    assert run.run_uid


def test_ensure_columns_adds_adr044_columns(tmp_path: Path) -> None:
    """Opening the store on a pre-ADR-044 DB adds the new run/result columns."""
    db = tmp_path / "test-results.db"
    _make_old_db(db)
    ResultStore(db_path=db)  # migrates in __init__

    cols_runs = {
        r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(test_runs)")
    }
    cols_results = {
        r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(test_results)")
    }
    assert {
        "trigger",
        "actor",
        "git_sha",
        "pool_size",
        "budget_seconds",
        "projected_seconds",
        "phase_timings",
        "shed_tests",
    } <= cols_runs
    assert {"status", "target", "distro", "image", "shard", "retry_of"} <= cols_results


def _passing_result(name: str = "good-app"):
    """A minimal passing TestResult stand-in (no bundle)."""
    test_name = name

    class _Tier:
        value = "fast"

    class _Prio:
        value = "P0"

    class _Test:
        runner_type = "deployment"
        tier = _Tier()
        priority = _Prio()
        name = test_name

    class _Result:
        passed = True
        total_duration = 0.5
        error = None
        deploy_logs = ""
        validation_results: ClassVar[list] = []
        bundle = None
        test = _Test()

    return _Result()


def test_save_derives_status_pass_and_fail(tmp_path: Path) -> None:
    db = tmp_path / "r.db"
    store = ResultStore(db_path=db)
    store.start_run(mode="ci", target_type="docker", target_name="t")

    store.save(_passing_result("good-app"))  # passed=True  -> status "pass"
    bundle = Bundle(
        run_id="rid-x",
        app="bad-app",
        target_kind="docker",
        classifier="proxy-502",
        headline="✗ proxy-502 — bad-app",
    )
    store.save(_result_with_bundle(bundle))  # passed=False -> status "fail"

    rows = dict(
        sqlite3.connect(db).execute("SELECT test_name, status FROM test_results")
    )
    assert rows["good-app"] == "pass"
    assert rows["bad-app"] == "fail"


def test_save_records_test_path_for_variant_derivation(tmp_path: Path) -> None:
    """The result stores the test's source path so the report can derive the
    packaging variant (docker/native/nix/…) — the bare test_name can't encode it."""
    db = tmp_path / "r.db"
    store = ResultStore(db_path=db)
    store.start_run(mode="ci", target_type="docker", target_name="t")

    result = _passing_result("bugsink")
    result.test.source_path = Path("apps/real-apps-docker/bugsink/hop3.toml")
    store.save(result)

    (path,) = (
        sqlite3.connect(db)
        .execute("SELECT test_path FROM test_results WHERE test_name = 'bugsink'")
        .fetchone()
    )
    assert path == "apps/real-apps-docker/bugsink/hop3.toml"


def _result_with_bundle(bundle: Bundle):
    """Minimal stand-in for runners.base.TestResult (stub, not mock)."""

    class _Tier:
        value = "fast"

    class _Prio:
        value = "P0"

    class _Test:
        name = bundle.app
        runner_type = "deployment"
        tier = _Tier()
        priority = _Prio()

    class _Result:
        test = _Test()
        passed = False
        total_duration = 1.0
        error = "boom"
        deploy_logs = ""
        validation_results: ClassVar[list] = []
        bundle = None

    r = _Result()
    r.bundle = bundle
    return r


def test_save_records_and_reads_back_bundle(tmp_path: Path) -> None:
    store = ResultStore(db_path=tmp_path / "r.db")
    store.start_run(mode="ci", target_type="docker", target_name="t")

    bundle = Bundle(
        run_id="2026-06-05T00-00-00Z-myapp-abc123",
        app="myapp",
        target_kind="docker",
        classifier="proxy-502",
        headline="✗ proxy-502 — myapp",
        sections={},
        artifact_dir=tmp_path / "test-runs" / "2026-06-05T00-00-00Z-myapp-abc123",
    )
    rid = store.save(_result_with_bundle(bundle))
    assert isinstance(rid, int)

    record = store.get_result_by_run_id("2026-06-05T00-00-00Z-myapp-abc123")
    assert record is not None
    assert record.classification == "proxy-502"
    headline = record.headline
    assert headline is not None
    assert headline.startswith("✗ proxy-502")
    bundle_path = record.bundle_path
    assert bundle_path is not None
    assert bundle_path.endswith("2026-06-05T00-00-00Z-myapp-abc123")


def test_ok_bundle_is_not_persisted(tmp_path: Path) -> None:
    store = ResultStore(db_path=tmp_path / "r.db")
    store.start_run(mode="ci", target_type="docker", target_name="t")
    bundle = Bundle(
        run_id="rid-ok",
        app="myapp",
        target_kind="docker",
        classifier="ok",
        headline="",
    )
    store.save(_result_with_bundle(bundle))
    assert store.get_result_by_run_id("rid-ok") is None


def test_run_uid_uniqueness_enforced_on_fresh_store(tmp_path: Path) -> None:
    """A FRESH DB rejects a duplicate run_uid. Regression for review #10: the
    model's `index=True` once created `ix_test_runs_run_uid`, and the unique
    index reused that name, so `CREATE UNIQUE INDEX IF NOT EXISTS` silently
    no-op'd and uniqueness was never enforced on new databases."""
    store = ResultStore(db_path=tmp_path / "fresh.db")
    with store.engine.begin() as conn:
        conn.execute(text("INSERT INTO test_runs (run_uid, mode) VALUES ('dup', 'ci')"))
    with pytest.raises(IntegrityError), store.engine.begin() as conn:
        conn.execute(text("INSERT INTO test_runs (run_uid, mode) VALUES ('dup', 'ci')"))
