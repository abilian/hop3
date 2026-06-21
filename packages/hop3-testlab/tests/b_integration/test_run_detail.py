# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The run-detail page renders a run's results + the regressions diff."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hop3_testing.results import ResultStore
from hop3_testing.results.models import TestResultRecord, TestRun
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hop3_testlab.web.asgi import create_app

if TYPE_CHECKING:
    from pathlib import Path


def _seed_run_with_failure(
    db_path: Path,
    run_uid: str,
    failing: str,
    *,
    finished: bool = True,
    metadata: dict | None = None,
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
            run_metadata=metadata
            if metadata is not None
            else {"os_name": "ubuntu", "os_version": "24.04"},
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
    # A finished run does NOT auto-refresh, and shows no manual Refresh button
    # (nothing left to update).
    assert 'http-equiv="refresh"' not in response.text
    assert "location.reload()" not in response.text


def test_run_detail_in_progress_is_accessible_and_live(tmp_path):
    """A still-running run's finished builds are viewable, with a running state
    and a manual Refresh button. There is NO meta-refresh: a periodic full
    reload would wipe scroll position, table sort/filter state, and any
    in-progress text selection while the operator reads the live run."""
    db = tmp_path / "test-results.db"
    _seed_run_with_failure(
        db, "2026-06-08T00-00-00Z-nightly-live1", "edrix", finished=False
    )

    with TestClient(app=create_app()) as client:
        response = client.get("/runs/2026-06-08T00-00-00Z-nightly-live1")

    assert response.status_code == 200
    assert "edrix" in response.text  # finished build, accessible mid-run
    assert "running" in response.text.lower()  # running indicator
    assert 'http-equiv="refresh"' not in response.text  # no disruptive auto-reload
    assert "location.reload()" in response.text  # manual Refresh button instead


def test_run_detail_table_is_sortable_and_shows_variant(tmp_path):
    """The results render as the Alpine sort/filter table with a variant chip."""
    db = tmp_path / "test-results.db"
    _seed_run_with_failure(
        db, "2026-06-09T00-00-00Z-nightly-var01", "apps/real-apps-docker/bugsink"
    )

    with TestClient(app=create_app()) as client:
        response = client.get("/runs/2026-06-09T00-00-00Z-nightly-var01")

    assert response.status_code == 200
    # Rows are embedded as JSON in a <script> tag (NOT in the x-data attribute,
    # whose double quotes would otherwise break on the JSON's quotes) and must
    # round-trip through json.loads — this is the regression guard for the
    # "empty table" bug.
    m = re.search(
        r'<script type="application/json" id="run-results">(.*?)</script>',
        response.text,
        re.DOTALL,
    )
    assert m, "results JSON <script> block missing"
    rows = json.loads(m.group(1))
    assert rows[0]["test_name"] == "apps/real-apps-docker/bugsink"
    assert rows[0]["variant"] == "docker"  # derived discriminator
    # Alpine reads the script tag — the data must NOT be inlined in the attribute.
    assert 'x-data="resultsTable()"' in response.text
    # The interactive table + controls are present.
    assert "failures only" in response.text


def test_run_detail_unknown_run_is_404(tmp_path):
    with TestClient(app=create_app()) as client:
        response = client.get("/runs/does-not-exist")
    assert response.status_code == 404


def _platform_ref_in_session_details(html: str) -> str | None:
    """The platform_ref value rendered in the Session details bag (or None)."""
    m = re.search(r"platform_ref</dt><dd[^>]*>([^<]+)</dd>", html)
    return m.group(1).strip() if m else None


def test_run_detail_shows_provenance_tuple(tmp_path):
    """The composition identity (source / apps_ref / platform_ref) renders in
    Session details — the dashboard says which composition this run was (§A)."""
    db = tmp_path / "test-results.db"
    _seed_run_with_failure(
        db,
        "2026-06-18T00-00-00Z-coverage-cmp1",
        "apps/x",
        metadata={
            "source_name": "main-repo",
            "apps_ref": "devel",
            "platform_ref": "main",
            "runner_version": "0.5.0",
        },
    )
    with TestClient(app=create_app()) as client:
        response = client.get("/runs/2026-06-18T00-00-00Z-coverage-cmp1")

    assert response.status_code == 200
    assert "apps_ref" in response.text
    assert "platform_ref" in response.text
    assert _platform_ref_in_session_details(response.text) == "main"


def test_run_detail_distinguishes_compositions_by_platform_ref(tmp_path):
    """Same apps@devel, two platform refs -> two distinct compositions, each
    page showing its own platform_ref (the heart of slice 1's value)."""
    db = tmp_path / "test-results.db"
    _seed_run_with_failure(
        db,
        "2026-06-18T00-00-00Z-cov-main",
        "apps/x",
        metadata={"apps_ref": "devel", "platform_ref": "main"},
    )
    _seed_run_with_failure(
        db,
        "2026-06-18T00-00-00Z-cov-devl",
        "apps/x",
        metadata={"apps_ref": "devel", "platform_ref": "devel"},
    )
    with TestClient(app=create_app()) as client:
        page_main = client.get("/runs/2026-06-18T00-00-00Z-cov-main").text
        page_devl = client.get("/runs/2026-06-18T00-00-00Z-cov-devl").text

    assert _platform_ref_in_session_details(page_main) == "main"
    assert _platform_ref_in_session_details(page_devl) == "devel"
