# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The /builds/<id> page renders a build's per-phase logs (progressive disclosure)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_testing.results import ResultStore
from hop3_testing.results.models import TestResultRecord, TestRun
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hop3_testlab.web.asgi import create_app

if TYPE_CHECKING:
    from pathlib import Path


def _seed_build(db_path: Path) -> int:
    store = ResultStore(db_path=db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        run = TestRun(
            run_uid="run-1", mode="nightly", target_type="ssh", target_name="t"
        )
        session.add(run)
        session.flush()
        rec = TestResultRecord(run_id=run.id, test_name="myapp", passed=True)
        session.add(rec)
        session.commit()
        rid = rec.id
    store.save_build_logs(
        rid,
        {"deploy": "uploading bits…\ndone", "verify": "[PASS] http (0.1s): 200 OK"},
        timings={"total_seconds": 2.0},
    )
    return rid


def test_build_detail_renders_phase_logs(tmp_path: Path):
    rid = _seed_build(tmp_path / "test-results.db")  # conftest set TESTLAB_DB_PATH

    with TestClient(app=create_app()) as client:
        response = client.get(f"/builds/{rid}")

    assert response.status_code == 200
    assert "deploy" in response.text
    assert "uploading bits" in response.text  # decompressed phase log
    assert "verify" in response.text


def test_build_detail_unknown_is_404(tmp_path: Path):
    with TestClient(app=create_app()) as client:
        response = client.get("/builds/99999")
    assert response.status_code == 404
