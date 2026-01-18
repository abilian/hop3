# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Result storage using SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base, TestResultRecord, TestRun, ValidationRecord

if TYPE_CHECKING:
    from hop3_testing.runners.base import TestResult


class ResultStore:
    """Stores and retrieves test results in SQLite."""

    DEFAULT_DB_PATH = Path.home() / ".hop3" / "test-results.db"

    def __init__(self, db_path: Path | None = None):
        """Initialize the result store.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.hop3/test-results.db
        """
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        self._current_run: TestRun | None = None

    def start_run(
        self,
        mode: str,
        target_type: str,
        target_name: str,
        hop3_version: str | None = None,
    ) -> TestRun:
        """Start a new test run.

        Args:
            mode: Execution mode (dev, ci, nightly, release, package)
            target_type: Target type (docker, remote)
            target_name: Target identifier
            hop3_version: Hop3 version being tested

        Returns:
            The created TestRun object
        """
        session = self.Session()
        try:
            run = TestRun(
                mode=mode,
                target_type=target_type,
                target_name=target_name,
                hop3_version=hop3_version,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            self._current_run = run
            return run
        finally:
            session.close()

    def save(self, result: TestResult) -> None:
        """Save a test result.

        Args:
            result: The TestResult to save
        """
        session = self.Session()
        try:
            record = TestResultRecord(
                run_id=self._current_run.id if self._current_run else None,
                test_name=result.test.name,
                category=result.test.category.value,
                tier=result.test.tier.value,
                priority=result.test.priority.value,
                passed=result.passed,
                duration=result.total_duration,
                error=result.error,
                logs=result.deploy_logs,
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

            session.commit()

            # Update run counts
            if self._current_run:
                # Refetch the run in this session
                run = session.get(TestRun, self._current_run.id)
                if run:
                    run.total_tests += 1
                    if result.passed:
                        run.passed_tests += 1
                    else:
                        run.failed_tests += 1
                    session.commit()

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

    def get_recent_runs(self, limit: int = 10) -> list[TestRun]:
        """Get recent test runs.

        Args:
            limit: Maximum number of runs to return

        Returns:
            List of recent TestRun objects
        """
        session = self.Session()
        try:
            return (
                session
                .query(TestRun)
                .order_by(TestRun.started_at.desc())
                .limit(limit)
                .all()
            )
        finally:
            session.close()

    def get_run(self, run_id: int) -> TestRun | None:
        """Get a specific run by ID.

        Args:
            run_id: Run ID

        Returns:
            TestRun object or None
        """
        session = self.Session()
        try:
            return session.get(TestRun, run_id)
        finally:
            session.close()

    def get_run_results(self, run_id: int) -> list[TestResultRecord]:
        """Get all results for a run.

        Args:
            run_id: Run ID

        Returns:
            List of TestResultRecord objects
        """
        session = self.Session()
        try:
            return (
                session
                .query(TestResultRecord)
                .filter(TestResultRecord.run_id == run_id)
                .order_by(TestResultRecord.executed_at)
                .all()
            )
        finally:
            session.close()

    def get_recent_failures(self, limit: int = 20) -> list[TestResultRecord]:
        """Get recent test failures.

        Args:
            limit: Maximum number of failures to return

        Returns:
            List of failed TestResultRecord objects
        """
        session = self.Session()
        try:
            return (
                session
                .query(TestResultRecord)
                .filter(TestResultRecord.passed == False)  # noqa: E712
                .order_by(TestResultRecord.executed_at.desc())
                .limit(limit)
                .all()
            )
        finally:
            session.close()
