# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""SQLAlchemy models for test result storage.

Columns keep ``nullable=True`` (the schema's long-standing shape — every
non-PK column is nullable) even where the ``Mapped[...]`` annotation is
non-optional: the annotation reflects how the code *uses* a loaded row
(these fields are populated in practice), while the relaxed DB constraint
keeps existing ``test-results.db`` files and partial inserts working.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base class for all models."""


class TestRun(Base):
    """A collection of test executions.

    Represents a single invocation of hop3-test, which may run
    multiple tests.
    """

    __tablename__ = "test_runs"
    __test__ = False  # SQLAlchemy model named Test*, not a pytest test class

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # No `index=True`: the partial UNIQUE index (`uq_test_runs_run_uid`, created
    # in store.py::_ensure_columns) is the run_uid index. A plain `index=True`
    # here created `ix_test_runs_run_uid`, and the unique index reused that exact
    # name, so `CREATE UNIQUE INDEX IF NOT EXISTS` silently no-op'd on fresh DBs —
    # uniqueness was never enforced (review #10).
    run_uid: Mapped[str | None] = mapped_column(String(80), nullable=True)
    """User-facing run handle (<ISO>-<target>-<shortid>); the `why`/`triage` key.
    Unique enforced via a partial index (see ResultStore._ensure_columns)."""

    mode: Mapped[str] = mapped_column(String(20), nullable=True)
    """Execution mode (dev, ci, nightly, release, package)."""

    target_type: Mapped[str] = mapped_column(String(20), nullable=True)
    """Target type (docker, remote)."""

    target_name: Mapped[str] = mapped_column(String(100), nullable=True)
    """Target identifier (e.g., container ID, hostname)."""

    hop3_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    """Hop3 version being tested."""

    total_tests: Mapped[int] = mapped_column(default=0, nullable=True)
    """Total number of tests run."""

    passed_tests: Mapped[int] = mapped_column(default=0, nullable=True)
    """Number of passing tests."""

    failed_tests: Mapped[int] = mapped_column(default=0, nullable=True)
    """Number of failing tests."""

    # --- ADR 044: provenance + budget bookkeeping (additive, nullable) --------
    trigger: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    """Who/what started the run: scheduled-nightly | cli:<user> | web:<user>."""

    actor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    """The user/agent that initiated the run."""

    git_sha: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    """Git SHA under test."""

    pool_size: Mapped[int] = mapped_column(default=1, nullable=True)
    """Number of provisioned targets (1 for CLI / v1)."""

    budget_seconds: Mapped[int | None] = mapped_column(nullable=True)
    """Wall-clock budget for the run (the 6 h nightly target)."""

    projected_seconds: Mapped[int | None] = mapped_column(nullable=True)
    """Projected duration from history (budget enforcement)."""

    phase_timings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    """Per-phase timings (INIT/RESET/DEPLOY/TEST/REPORT)."""

    shed_tests: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    """Tests dropped under budget pressure (recorded, never silently)."""

    run_metadata: Mapped[dict | None] = mapped_column(JSON, default=dict, nullable=True)
    """Extensible session-metadata bag (target OS name/version, server type,
    datacenter, image, …). Progressive-disclosure detail; the named columns
    (hop3_version, git_sha) stay queryable. NB: can't be named ``metadata`` —
    that attribute is reserved by SQLAlchemy's declarative base."""

    planned_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Planned test count per type at selection time, e.g.
    ``{"app": 50, "demo": 8, "tutorial": 35}``. Recorded by the engine at
    ``start_run`` so the live dashboard can show "M done / N planned" per type
    (the planned totals aren't otherwise visible to the web app)."""

    # Relationships
    results: Mapped[list[TestResultRecord]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    @property
    def duration(self) -> float | None:
        """Get run duration in seconds."""
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class TestResultRecord(Base):
    """Individual test result."""

    __tablename__ = "test_results"
    __test__ = False  # SQLAlchemy model named Test*, not a pytest test class

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), nullable=True)

    test_name: Mapped[str] = mapped_column(String(100), nullable=True)
    """Test identifier."""

    category: Mapped[str] = mapped_column(String(20), nullable=True)
    """Test category (deployment, demo, tutorial)."""

    tier: Mapped[str] = mapped_column(String(20), nullable=True)
    """Test tier (fast, medium, slow, very-slow)."""

    priority: Mapped[str] = mapped_column(String(5), nullable=True)
    """Test priority (P0, P1, P2)."""

    passed: Mapped[bool] = mapped_column(nullable=True)
    """Whether the test passed."""

    duration: Mapped[float] = mapped_column(Float, nullable=True)
    """Execution time in seconds."""

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Error message if test failed."""

    logs: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Deployment/execution logs."""

    bundle_run_id: Mapped[str | None] = mapped_column(
        String(80), index=True, nullable=True
    )
    """Diagnostic bundle id (<ISO>-<app>-<shortid>); the `hop3-test why` key."""

    bundle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Absolute path to ~/.hop3/test-runs/<run_id>/."""

    classification: Mapped[str | None] = mapped_column(String(24), nullable=True)
    """Failure classifier (proxy-502, build-failure, app-crash, ...)."""

    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    """The <=12-line diagnostic headline (so `why` shows it without disk read)."""

    # --- ADR 044: status + target context + retry linkage (additive) ----------
    status: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    """Outcome: pass | fail | skip | error | flaky. Derived from ``passed`` for
    now; the worker sets the richer states (skip/error/flaky) later."""

    target: Mapped[str | None] = mapped_column(String(100), nullable=True)
    """Target identifier the test ran on (per-target trends)."""

    distro: Mapped[str | None] = mapped_column(String(40), nullable=True)
    """Target distro (multi-distro trends)."""

    image: Mapped[str | None] = mapped_column(String(120), nullable=True)
    """Target base image."""

    shard: Mapped[int | None] = mapped_column(nullable=True)
    """Which shard ran this test (sharded fan-out); NULL for single-target runs."""

    retry_of: Mapped[int | None] = mapped_column(
        ForeignKey("test_results.id"), nullable=True
    )
    """Link to the original result when this is a re-run (feeds flakiness)."""

    phase_timings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    """Per-build phase durations in seconds (prepare/build/deploy/verify)."""

    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=True,
    )
    """When the test was executed."""

    __table_args__ = (
        # ADR 044 §data-model: the trend/diff query indexes.
        Index("ix_test_results_name_executed", "test_name", "executed_at"),
        Index("ix_test_results_run_status", "run_id", "status"),
    )

    # Relationships
    run: Mapped[TestRun] = relationship(back_populates="results")
    validations: Mapped[list[ValidationRecord]] = relationship(
        back_populates="test_result", cascade="all, delete-orphan"
    )


class ValidationRecord(Base):
    """Individual validation result within a test."""

    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_result_id: Mapped[int] = mapped_column(
        ForeignKey("test_results.id"), nullable=True
    )

    validation_type: Mapped[str] = mapped_column(String(20), nullable=True)
    """Validation type (http, command, script, etc.)."""

    passed: Mapped[bool] = mapped_column(nullable=True)
    """Whether the validation passed."""

    message: Mapped[str] = mapped_column(Text, nullable=True)
    """Result message."""

    duration: Mapped[float] = mapped_column(Float, nullable=True)
    """Validation duration in seconds."""

    # Relationships
    test_result: Mapped[TestResultRecord] = relationship(back_populates="validations")


class RunLease(Base):
    """A lightweight lease so two runs don't claim the same target (ADR 044 §D).

    One row per target; ``expires_at`` is an epoch timestamp (Float) to avoid
    SQLite's tz-naive datetime comparison pitfalls. A crashed holder's lease is
    reclaimable once expired (the prod path will use a Postgres advisory lock,
    which auto-releases on crash; see the spec).
    """

    __tablename__ = "run_lease"
    __test__ = False  # SQLAlchemy model named *Run*/Lease, not a pytest test class

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[str] = mapped_column(
        String(120), unique=True, index=True, nullable=True
    )
    holder: Mapped[str] = mapped_column(String(120), nullable=True)
    """Who holds it: scheduled-nightly | cli:<user> | web:<user>."""
    run_uid: Mapped[str | None] = mapped_column(String(80), nullable=True)
    acquired_at: Mapped[float] = mapped_column(Float, nullable=True)
    expires_at: Mapped[float] = mapped_column(Float, nullable=True)
    pid: Mapped[int | None] = mapped_column(nullable=True)
    """PID of the engine subprocess (spawned in its own session/group) so the
    dashboard can stop a running session via ``os.killpg``. Null until the
    worker has spawned the engine (a brief 'starting' window)."""
    pid_starttime: Mapped[int | None] = mapped_column(nullable=True)
    """The engine PID's start-time (jiffies, ``/proc/<pid>/stat`` field 22). The
    kernel never reissues the same (pid, starttime) pair, so the stop control can
    confirm the PID still refers to *our* engine before signalling — guarding
    against killing an unrelated process that recycled the PID."""


class BuildLog(Base):
    """A compressed per-phase log for one build (ADR 044 §E).

    Full logs are kept for every build (pass or fail), so the payload is stored
    compressed (see ``compression``); ``algo`` tags the codec for forward-compat.
    Pruned by retention policy.
    """

    __tablename__ = "build_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_result_id: Mapped[int] = mapped_column(
        ForeignKey("test_results.id"), index=True, nullable=True
    )
    phase: Mapped[str] = mapped_column(String(32), nullable=True)
    """Build phase: prepare | build | deploy | verify | … (free-form)."""
    algo: Mapped[str] = mapped_column(String(16), nullable=True)
    """Compression codec (e.g. "lzma")."""
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    """Compressed UTF-8 log text."""
    size: Mapped[int] = mapped_column(nullable=True)
    """Original (uncompressed) size in bytes."""
