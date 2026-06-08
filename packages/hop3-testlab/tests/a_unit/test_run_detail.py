# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The run-detail page renders a run's results + the regressions diff."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hop3_testing.results import ResultStore
from hop3_testing.results.models import TestResultRecord, TestRun
from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from pathlib import Path


def _seed_run_with_failure(
    db_path: Path, run_uid: str, failing: str, *, finished: bool = True
) -> None:
    ResultStore(db_path=db_path)  # ensure schema
    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        run = TestRun(
            run_uid=run_uid,
            mode="nightly",
            target_type="docker",
            target_name="hetzner-1",
            total_tests=1,
            passed_tests=0,
            failed_tests=1,
            hop3_version="0.5.0",
            git_sha="deadbee",
            run_metadata={"os_name": "ubuntu", "os_version": "24.04"},
            # In-progress runs have no finished_at; a finished one does.
            finished_at=datetime.now(UTC) if finished else None,
        )
        session.add(run)
        session.flush()
        session.add(
            TestResultRecord(
                run_id=run.id,
                test_name=failing,
                passed=False,
                status="fail",
                classification="proxy-502",
                headline=f"x proxy-502 - {failing}",
                duration=1.0,
            )
        )
        session.commit()


def test_run_detail_shows_results_and_regressions(tmp_path):
    db = tmp_path / "test-results.db"  # conftest set TESTLAB_DB_PATH to this
    _seed_run_with_failure(db, "2026-06-06T00-00-00Z-nightly-abc123", "focalboard")

    with TestClient(app=create_app()) as client:
        response = client.get("/runs/2026-06-06T00-00-00Z-nightly-abc123")

    assert response.status_code == 200
    assert "focalboard" in response.text  # the failing test is listed
    assert "proxy-502" in response.text  # its classifier
    # No previous run -> no diff section (nothing to compare against).
    # Session details (progressive disclosure): named fields + the metadata bag.
    assert "Session details" in response.text
    assert "0.5.0" in response.text  # hop3 version
    assert "ubuntu" in response.text  # from run_metadata
    # A finished run does NOT auto-refresh.
    assert 'http-equiv="refresh"' not in response.text


def test_run_detail_in_progress_is_accessible_and_live(tmp_path):
    """A still-running run's finished builds are viewable, with a running state
    and auto-refresh so new builds appear."""
    db = tmp_path / "test-results.db"
    _seed_run_with_failure(
        db, "2026-06-08T00-00-00Z-nightly-live1", "edrix", finished=False
    )

    with TestClient(app=create_app()) as client:
        response = client.get("/runs/2026-06-08T00-00-00Z-nightly-live1")

    assert response.status_code == 200
    assert "edrix" in response.text  # finished build, accessible mid-run
    assert "running" in response.text.lower()  # running indicator
    assert 'http-equiv="refresh"' in response.text  # auto-refreshes while in progress


def test_run_detail_unknown_run_is_404(tmp_path):
    with TestClient(app=create_app()) as client:
        response = client.get("/runs/does-not-exist")
    assert response.status_code == 404
