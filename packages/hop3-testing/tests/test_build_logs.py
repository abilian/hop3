# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Per-build logs: compression + store save/get + retention pruning (ADR 044)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from hop3_testing.results import ResultStore
from hop3_testing.results.compression import compress, decompress
from hop3_testing.results.models import TestResultRecord, TestRun
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from pathlib import Path


def test_compress_roundtrip_and_shrinks():
    text = "deploy log line\n" * 500
    algo, blob, size = compress(text)
    assert algo == "lzma"
    assert size == len(text.encode())
    assert len(blob) < size  # actually compressed
    assert decompress(algo, blob) == text


def _seed_result(db_path: Path, run_uid: str = "run-1") -> tuple[ResultStore, int]:
    store = ResultStore(db_path=db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as s:
        run = TestRun(
            run_uid=run_uid, mode="nightly", target_type="ssh", target_name="t"
        )
        s.add(run)
        s.flush()
        rec = TestResultRecord(run_id=run.id, test_name="app", passed=True)
        s.add(rec)
        s.commit()
        return store, rec.id


def test_save_and_get_build_logs(tmp_path: Path):
    store, rid = _seed_result(tmp_path / "r.db")
    store.save_build_logs(
        rid,
        {"build": "compiling…\nok", "deploy": "uploading…\ndone", "verify": ""},
        timings={"build": 12.5, "deploy": 4.0},
    )

    logs = store.get_build_logs(rid)
    phases = {entry["phase"]: entry["text"] for entry in logs}
    assert phases["build"].startswith("compiling")
    assert phases["deploy"].endswith("done")
    assert "verify" not in phases  # empty logs are skipped


def test_prune_keeps_recent_runs_only(tmp_path: Path):
    db = tmp_path / "r.db"
    store = ResultStore(db_path=db)
    engine = create_engine(f"sqlite:///{db}")

    result_ids = []
    with Session(engine) as s:
        for i in range(3):  # 3 runs, oldest first
            run = TestRun(
                run_uid=f"run-{i}", mode="nightly", target_type="ssh", target_name="t"
            )
            s.add(run)
            s.flush()
            rec = TestResultRecord(run_id=run.id, test_name="app", passed=True)
            s.add(rec)
            s.flush()
            result_ids.append(rec.id)
            time.sleep(0.01)  # ensure distinct started_at ordering
        s.commit()
    for rid in result_ids:
        store.save_build_logs(rid, {"deploy": "log"})

    deleted = store.prune_build_logs(keep_runs=1)  # keep newest run only

    assert deleted == 2  # the two older runs' logs removed
    assert store.get_build_logs(result_ids[-1])  # newest kept
    assert store.get_build_logs(result_ids[0]) == []  # oldest pruned


def test_save_captures_per_build_logs_for_passing_build(tmp_path: Path):
    store = ResultStore(db_path=tmp_path / "s.db")
    store.start_run(mode="ci", target_type="docker", target_name="t")
    test = SimpleNamespace(
        name="myapp",
        runner_type="deployment",
        tier=SimpleNamespace(value="fast"),
        priority=SimpleNamespace(value="P0"),
    )
    val = SimpleNamespace(passed=True, message="200 OK", duration=0.1, type_name="http")
    result = SimpleNamespace(
        test=test,
        passed=True,
        total_duration=2.0,
        error=None,
        deploy_logs="compiling…\nuploading…\nok",
        runtime_logs="",
        validation_results=[val],
        bundle=None,
    )

    rid = store.save(cast("Any", result))

    assert isinstance(rid, int)
    logs = {e["phase"]: e["text"] for e in store.get_build_logs(rid)}
    assert "uploading" in logs["deploy"]  # deploy phase, even though it passed
    assert "PASS" in logs["verify"]  # verify phase synthesized from validations
    assert "runtime" not in logs  # empty phase -> skipped


def test_store_engine_uses_wal_and_busy_timeout(tmp_path: Path):
    # So CLI writes and a concurrent dashboard read don't "database is locked".
    store = ResultStore(db_path=tmp_path / "wal.db")
    with store.engine.connect() as conn:
        journal = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        busy = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
    assert journal.lower() == "wal"
    assert busy == 30000
