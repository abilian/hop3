# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The /trends page surfaces flaky tests across runs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from hop3_testing.results import ResultStore
from hop3_testing.results.models import TestResultRecord, TestRun
from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from pathlib import Path


def test_trends_page_lists_flaky_test(tmp_path: Path):
    db = tmp_path / "test-results.db"  # conftest set TESTLAB_DB_PATH here
    ResultStore(db_path=db)
    engine = create_engine(f"sqlite:///{db}")
    base = datetime(2026, 6, 6, tzinfo=timezone.utc)
    with Session(engine) as session:
        for i, passed in enumerate([True, False]):  # "wobbler" flips once
            run = TestRun(
                run_uid=f"run-{i}",
                mode="nightly",
                target_type="docker",
                target_name="t",
                started_at=base + timedelta(minutes=i),
                total_tests=1,
                passed_tests=1 if passed else 0,
                failed_tests=0 if passed else 1,
            )
            session.add(run)
            session.flush()
            session.add(
                TestResultRecord(run_id=run.id, test_name="wobbler", passed=passed)
            )
        session.commit()

    with TestClient(app=create_app()) as client:
        response = client.get("/trends")

    assert response.status_code == 200
    assert "wobbler" in response.text
