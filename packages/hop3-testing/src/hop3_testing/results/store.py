# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Result storage using SQLite."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from hop3_testing.bundle_ids import make_run_id

from .compression import compress, decompress
from .models import Base, BuildLog, TestResultRecord, TestRun, ValidationRecord

if TYPE_CHECKING:
    from hop3_testing.runners.base import TestResult


def _detect_git_sha() -> str | None:
    """Best-effort short git SHA of the code under test (None outside a repo)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _detect_hop3_version() -> str | None:
    """Best-effort installed Hop3 version (None if not installed)."""
    for pkg in ("hop3-server", "hop3"):
        try:
            return _pkg_version(pkg)
        except PackageNotFoundError:
            continue
    return None


def _configure_sqlite_conn(dbapi_conn, _record) -> None:
    """WAL + busy_timeout so CLI writes and a Test Lab dashboard read coexist.

    Without these, a write in progress makes a concurrent reader's DDL/query fail
    immediately ("database is locked") -> a transient 500 in the dashboard.
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def _derive_status(result) -> str:
    """Map a result to pass/fail, or xfail/xpass for negative tests.

    A "bad recipe" (expects_failure) is inverted by the runner: a failed deploy
    yields ``result.passed=True``. So passed True -> the expected failure happened
    (xfail); False -> it unexpectedly worked (xpass — notable, surfaced).
    """
    if getattr(result.test, "expects_failure", False):
        return "xfail" if result.passed else "xpass"
    return "pass" if result.passed else "fail"


def _format_validations(validations) -> str:
    """Render validation results as a human-readable verify-phase log."""
    lines = []
    for v in validations:
        mark = "PASS" if v.passed else "FAIL"
        dur = f"{v.duration:.2f}s" if v.duration is not None else "—"
        lines.append(f"[{mark}] {v.type_name} ({dur}): {v.message}")
    return "\n".join(lines)


def store_url(target: object) -> str:
    """SQLAlchemy URL for ``target``: a DSN (``postgresql+psycopg://…``) passes
    through; a filesystem path becomes a ``sqlite:///`` URL."""
    text = str(target)
    return text if "://" in text else f"sqlite:///{text}"


def make_store_engine(target: object):
    """Create the result-store engine, dialect-aware.

    SQLite gets ``check_same_thread=False`` + the concurrency PRAGMAs (so CLI
    writes and a dashboard read coexist without "database is locked"); Postgres
    gets a plain engine. ``target`` is a path (→ SQLite) or a DSN string.
    """
    url = store_url(target)
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _configure_sqlite_conn)
        return engine
    return create_engine(url)


class ResultStore:
    """Stores and retrieves test results (SQLite by default, or Postgres)."""

    DEFAULT_DB_PATH = Path.home() / ".hop3" / "test-results.db"

    def __init__(self, db_path: Path | str | None = None):
        """Initialize the result store.

        Args:
            db_path: a SQLite path (default ~/.hop3/test-results.db) or a
                SQLAlchemy DSN string for Postgres (``postgresql+psycopg://…``).
        """
        # An explicit db_path wins; else honor HOP3_TEST_RESULTS_DB (set by the
        # Test Lab worker so the engine subprocess writes to the Lab's store — a
        # SQLite path or a Postgres DSN), else the default local SQLite file.
        target = (
            db_path
            if db_path is not None
            else os.environ.get("HOP3_TEST_RESULTS_DB") or self.DEFAULT_DB_PATH
        )
        # SQLite has a file (ensure its dir exists); a Postgres DSN has neither.
        self.db_path = Path(target) if "://" not in str(target) else None
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = make_store_engine(target)
        Base.metadata.create_all(self.engine)
        self._ensure_columns()
        self.Session = sessionmaker(bind=self.engine)

        self._current_run: TestRun | None = None

    def _ensure_columns(self) -> None:
        """Add columns missing from a pre-existing DB.

        ``Base.metadata.create_all`` never ALTERs existing tables, so a DB created
        before the bundle columns were added would raise ``no such column`` on the
        first query. This additive migration keeps existing ``test-results.db``
        files working (SQLite supports ``ALTER TABLE ... ADD COLUMN``).
        """
        specs = {
            "test_runs": [
                ("run_uid", "VARCHAR(80)"),
                # ADR 044 provenance + budget bookkeeping
                ("trigger", "VARCHAR(64)"),
                ("actor", "VARCHAR(80)"),
                ("git_sha", "VARCHAR(40)"),
                ("pool_size", "INTEGER"),
                ("budget_seconds", "INTEGER"),
                ("projected_seconds", "INTEGER"),
                ("phase_timings", "JSON"),
                ("shed_tests", "JSON"),
                ("run_metadata", "JSON"),
                ("planned_counts", "JSON"),
            ],
            "run_lease": [
                # ADR 044: killable engine PID so the dashboard can stop a run,
                # plus its start-time so a recycled PID is never signalled.
                ("pid", "INTEGER"),
                ("pid_starttime", "INTEGER"),
            ],
            "test_results": [
                ("test_path", "TEXT"),
                ("bundle_run_id", "VARCHAR(80)"),
                ("bundle_path", "TEXT"),
                ("classification", "VARCHAR(24)"),
                ("headline", "TEXT"),
                # ADR 044 status + target context + retry linkage
                ("status", "VARCHAR(12)"),
                ("target", "VARCHAR(100)"),
                ("distro", "VARCHAR(40)"),
                ("image", "VARCHAR(120)"),
                ("shard", "INTEGER"),
                ("retry_of", "INTEGER"),
                ("phase_timings", "JSON"),
            ],
        }
        inspector = inspect(self.engine)
        for table, cols in specs.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, sqltype in cols:
                if name in existing:
                    continue
                # Each ALTER in its OWN transaction: on Postgres a failed statement
                # aborts the whole transaction, so a tolerated duplicate must not
                # poison the rest. Quote the name so reserved words (`trigger`) work.
                try:
                    with self.engine.begin() as conn:
                        conn.exec_driver_sql(
                            f'ALTER TABLE {table} ADD COLUMN "{name}" {sqltype}'
                        )
                except (OperationalError, ProgrammingError) as e:
                    # Tolerate only "already exists" (a concurrent xdist init beat
                    # us); any other migration error is real — fail loud.
                    text = str(e).lower()
                    if "exist" not in text and "duplicate" not in text:
                        raise
        with self.engine.begin() as conn:
            # UNIQUE can't ride a plain ADD COLUMN on a populated table; use a
            # partial index that tolerates the NULLs of pre-existing rows.
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_test_runs_run_uid "
                "ON test_runs(run_uid) WHERE run_uid IS NOT NULL"
            )
            # ADR 044 §data-model: trend/diff query indexes (also added to
            # existing DBs that predate them).
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_test_results_name_executed "
                "ON test_results(test_name, executed_at)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_test_results_run_status "
                "ON test_results(run_id, status)"
            )

    def start_run(
        self,
        mode: str,
        target_type: str,
        target_name: str,
        hop3_version: str | None = None,
        *,
        trigger: str | None = None,
        git_sha: str | None = None,
        metadata: dict | None = None,
        planned_counts: dict | None = None,
    ) -> TestRun:
        """Start a new test run.

        Args:
            mode: Execution mode (dev, ci, nightly, release, package)
            target_type: Target type (docker, remote)
            target_name: Target identifier
            hop3_version: Hop3 version being tested (auto-detected if omitted)
            trigger: provenance label (defaults from $HOP3_TEST_TRIGGER, else cli)
            git_sha: code SHA under test (auto-detected if omitted)
            metadata: extensible session metadata; merged with $HOP3_TEST_META
                (a JSON object) so the worker can inject target/OS details
                without changing this call site.

        Returns:
            The created TestRun object
        """
        meta = dict(metadata or {})
        env_meta = os.environ.get("HOP3_TEST_META")
        if env_meta:
            # Fail loud: a malformed payload must not silently drop run provenance
            # (it's set by the worker via json.dumps, so bad data is a real bug).
            try:
                meta.update(json.loads(env_meta))
            except (ValueError, TypeError) as e:
                msg = (
                    f"HOP3_TEST_META is not a valid JSON object: {e}. "
                    "Expected a JSON object (the worker sets it via json.dumps)."
                )
                raise ValueError(msg) from e

        session = self.Session()
        try:
            run = TestRun(
                run_uid=make_run_id(target_name or target_type),
                mode=mode,
                target_type=target_type,
                target_name=target_name,
                hop3_version=hop3_version or _detect_hop3_version(),
                # Provenance (ADR 044 §D): who/what started it + the code SHA, so
                # scheduled-nightly / cli / web runs are distinguishable and
                # filterable. Default trigger from env so the worker can tag a
                # subprocess run without changing call sites.
                trigger=trigger or os.environ.get("HOP3_TEST_TRIGGER", "cli"),
                git_sha=git_sha if git_sha is not None else _detect_git_sha(),
                run_metadata=meta or None,
                planned_counts=planned_counts,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            session.expunge(run)
            self._current_run = run
            return run
        finally:
            session.close()

    def save(self, result: TestResult) -> int | None:
        """Save a test result, returning the new record id.

        Records the diagnostic bundle pointer (bundle_run_id / bundle_path /
        classification / headline) when ``result.bundle`` is present and the run
        actually failed (an ``ok`` classification is not persisted).
        """
        bundle = getattr(result, "bundle", None)
        b_run_id = b_path = b_class = b_headline = None
        if bundle is not None and bundle.classifier != "ok":
            b_run_id = bundle.run_id
            b_path = str(bundle.artifact_dir) if bundle.artifact_dir else None
            b_class = bundle.classifier
            b_headline = bundle.headline
        status = _derive_status(result)
        session = self.Session()
        try:
            record = TestResultRecord(
                run_id=self._current_run.id if self._current_run else None,
                test_name=result.test.name,
                # The path encodes the packaging variant; test_name (a bare id)
                # does not. Stored so the report can show docker/native/nix/…
                test_path=(
                    str(src)
                    if (src := getattr(result.test, "source_path", None))
                    else None
                ),
                category=result.test.runner_type,
                tier=result.test.tier.value,
                priority=result.test.priority.value,
                passed=result.passed,
                status=status,
                duration=result.total_duration,
                error=result.error,
                logs=result.deploy_logs,
                bundle_run_id=b_run_id,
                bundle_path=b_path,
                classification=b_class,
                headline=b_headline,
            )
            session.add(record)

            # Save validation results
            for val_result in result.validation_results:
                val_record = ValidationRecord(
                    test_result=record,
                    validation_type=val_result.type_name,
                    passed=val_result.passed,
                    message=val_result.message,
                    duration=val_result.duration,
                )
                session.add(val_record)

            # Per-build logs (ADR 044 §E): full per-phase logs for EVERY build,
            # compressed (the failure diagnostic bundle is stored separately).
            session.flush()  # assign record.id for the build-log rows
            phase_logs = {
                "deploy": result.deploy_logs,
                "runtime": getattr(result, "runtime_logs", ""),
                "verify": _format_validations(result.validation_results),
            }
            for phase, text in phase_logs.items():
                if text:
                    algo, blob, size = compress(text)
                    session.add(
                        BuildLog(
                            test_result_id=record.id,
                            phase=phase,
                            algo=algo,
                            data=blob,
                            size=size,
                        )
                    )
            record.phase_timings = {"total_seconds": result.total_duration}

            session.commit()
            record_id: int | None = record.id

            # Update run counts
            if self._current_run:
                # Refetch the run in this session
                run = session.get(TestRun, self._current_run.id)
                if run:
                    run.total_tests = int(run.total_tests or 0) + 1
                    # Only a TRUE failure is red; xfail/xpass (negative tests)
                    # and pass count as "not a failure".
                    if status == "fail":
                        run.failed_tests = int(run.failed_tests or 0) + 1
                    else:
                        run.passed_tests = int(run.passed_tests or 0) + 1
                    session.commit()

            return record_id
        finally:
            session.close()

    def finish_run(self) -> None:
        """Mark current run as finished."""
        if self._current_run:
            session = self.Session()
            try:
                run = session.get(TestRun, self._current_run.id)
                if run:
                    run.finished_at = datetime.now(tz=timezone.utc)
                    session.commit()
            finally:
                session.close()
            self._current_run = None

    # -- Read API (for `hop3-test why` / `triage`) -------------------------- #

    def get_result_by_run_id(self, bundle_run_id: str) -> TestResultRecord | None:
        """Return the failed-test record carrying ``bundle_run_id`` (the `why` key)."""
        session = self.Session()
        try:
            record = (
                session
                .query(TestResultRecord)
                .filter(TestResultRecord.bundle_run_id == bundle_run_id)
                .order_by(TestResultRecord.id.desc())
                .first()
            )
            if record is not None:
                session.expunge(record)
            return record
        finally:
            session.close()

    def get_run(self, run_uid: str) -> TestRun | None:
        """Return the run with this user-facing ``run_uid``."""
        session = self.Session()
        try:
            run = (
                session.query(TestRun).filter(TestRun.run_uid == run_uid).one_or_none()
            )
            if run is not None:
                session.expunge(run)
            return run
        finally:
            session.close()

    def list_recent(self, limit: int = 20) -> list[TestRun]:
        """Return the most recent runs (newest first), for `triage`."""
        session = self.Session()
        try:
            runs = (
                session
                .query(TestRun)
                .order_by(TestRun.started_at.desc())
                .limit(limit)
                .all()
            )
            for run in runs:
                session.expunge(run)
            return runs
        finally:
            session.close()

    def get_failed_results(self, run: TestRun) -> list[TestResultRecord]:
        """Return the failed-test records (with a bundle) for a run."""
        session = self.Session()
        try:
            records = (
                session
                .query(TestResultRecord)
                .filter(
                    TestResultRecord.run_id == run.id,
                    TestResultRecord.bundle_run_id.isnot(None),
                )
                .order_by(TestResultRecord.id.asc())
                .all()
            )
            for record in records:
                session.expunge(record)
            return records
        finally:
            session.close()

    def previous_failures(self, mode: str, target_type: str) -> set[str]:
        """Names of tests that failed in the most recent FINISHED run of this
        family (same ``mode`` + ``target_type``).

        Used to run the previous run's failures first, so a re-run surfaces
        regressions fast. "Failed" means ``passed is False`` — a true failure;
        an expected negative-test failure is recorded as passed=True (xfail).
        """
        session = self.Session()
        try:
            run = (
                session
                .query(TestRun)
                .filter(
                    TestRun.mode == mode,
                    TestRun.target_type == target_type,
                    TestRun.finished_at.isnot(None),
                )
                .order_by(TestRun.started_at.desc())
                .first()
            )
            if run is None:
                return set()
            rows = (
                session
                .query(TestResultRecord.test_name)
                .filter(
                    TestResultRecord.run_id == run.id,
                    TestResultRecord.passed.is_(False),
                )
                .all()
            )
            return {name for (name,) in rows}
        finally:
            session.close()

    def save_build_logs(
        self,
        test_result_id: int,
        logs: dict[str, str],
        timings: dict[str, float] | None = None,
    ) -> None:
        """Persist per-phase logs (compressed) + optional timings for a build."""
        session = self.Session()
        try:
            for phase, text in logs.items():
                if not text:
                    continue
                algo, blob, size = compress(text)
                session.add(
                    BuildLog(
                        test_result_id=test_result_id,
                        phase=phase,
                        algo=algo,
                        data=blob,
                        size=size,
                    )
                )
            if timings is not None:
                record = session.get(TestResultRecord, test_result_id)
                if record is not None:
                    record.phase_timings = timings
            session.commit()
        finally:
            session.close()

    def get_build_logs(self, test_result_id: int) -> list[dict]:
        """Return decompressed per-phase logs for a build, in insertion order."""
        session = self.Session()
        try:
            rows = (
                session
                .query(BuildLog)
                .filter(BuildLog.test_result_id == test_result_id)
                .order_by(BuildLog.id.asc())
                .all()
            )
            return [
                {"phase": r.phase, "text": decompress(r.algo, r.data), "size": r.size}
                for r in rows
            ]
        finally:
            session.close()

    def prune_build_logs(self, keep_runs: int) -> int:
        """Delete build logs for all but the most recent ``keep_runs`` runs.

        Returns the number of BuildLog rows deleted. Deletes per-run to stay
        under SQLite's bound-parameter limit on the ``IN`` clause.
        """
        session = self.Session()
        try:
            all_run_ids = [
                r.id
                for r in session
                .query(TestRun.id)
                .order_by(TestRun.started_at.desc())
                .all()
            ]
            deleted = 0
            for run_id in all_run_ids[keep_runs:]:  # everything older than keep_runs
                result_ids = [
                    r.id
                    for r in session.query(TestResultRecord.id).filter(
                        TestResultRecord.run_id == run_id
                    )
                ]
                if result_ids:
                    deleted += (
                        session
                        .query(BuildLog)
                        .filter(BuildLog.test_result_id.in_(result_ids))
                        .delete(synchronize_session=False)
                    )
            session.commit()
            return deleted
        finally:
            session.close()
