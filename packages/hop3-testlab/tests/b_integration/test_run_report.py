# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The narrative run report: actionable markdown + the /report.md export."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import markdown
from hop3_testing.results import ResultStore
from hop3_testing.results.models import TestResultRecord, TestRun
from hop3_testlab.reports import build_run_report_md
from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from pathlib import Path


def _run() -> dict:
    return {
        "run_uid": "2026-06-10T00-00-00Z-nightly-xyz",
        "mode": "nightly",
        "target_type": "docker",
        "target_name": "hetzner-1",
        "total": 4,
        "passed": 1,
        "failed": 3,
        "duration": 42.5,
        "git_sha": "deadbee",
        "started_at": "2026-06-10 00:00:00Z",
        "finished_at": datetime(2026, 6, 10, 0, 5, tzinfo=UTC),
    }


def _results() -> list[dict]:
    return [
        {
            "id": 1,
            "test_name": "apps/real-apps-docker/ghost",
            "app": "ghost",
            "variant": "docker",
            "category": "deployment",
            "priority": "P1",
            "passed": False,
            "status": "fail",
            "classification": "build-failure",
            "headline": "x build-failure — ghost\nverdict: npm ERR!",
            "duration": 12.0,
            "error": "npm ERR!",
            "bundle_run_id": "bundle-ghost",
        },
        {
            "id": 2,
            "test_name": "demos/demo14",
            "app": "demo14",
            "variant": "demo",
            "category": "demo",
            "priority": "P1",
            "passed": False,
            "status": "fail",
            "classification": "timeout",
            "headline": None,
            "duration": 600.0,
            "error": "Demo timed out after 600s",
            "bundle_run_id": "bundle-demo14",
        },
        {
            "id": 3,
            "test_name": "apps/x/redis-app",
            "app": "redis-app",
            "variant": "native",
            "category": "deployment",
            "priority": "P0",
            "passed": False,
            "status": "fail",
            "classification": "addon-unreachable",
            "headline": "x addon-unreachable — redis-app",
            "duration": 5.0,
            "error": None,
            "bundle_run_id": None,
        },
        {
            "id": 4,
            "test_name": "apps/x/ok-app",
            "app": "ok-app",
            "variant": "docker",
            "category": "deployment",
            "priority": "P0",
            "passed": True,
            "status": "pass",
            "classification": None,
            "headline": None,
            "duration": 1.0,
            "error": None,
            "bundle_run_id": None,
        },
    ]


def test_report_groups_failures_by_classification_with_links():
    md = build_run_report_md(
        _run(), _results(), {"regressions": ["apps/real-apps-docker/ghost"]}
    )
    # Header summary.
    assert "# Run 2026-06-10T00-00-00Z-nightly-xyz" in md
    assert "1/4 passed" in md
    # Regressions surfaced first.
    assert "## Regressions (1)" in md
    # Grouped failure sections (friendly bucket headings).
    assert "## Failures (3)" in md
    assert "### Build failures (1)" in md
    assert "### Addon unreachable (1)" in md
    assert "### Timeouts" in md
    # Diagnostic headline + links.
    assert "x build-failure — ghost" in md
    assert "[build page](/builds/1)" in md
    assert "[logs / bundle](/bundle/bundle-ghost)" in md
    # A failure with no headline still gets a `why` command from its bundle id.
    assert "hop3-test why bundle-demo14 --section timeout" in md
    # Passing is a count, not an enumeration.
    assert "## Passing" in md
    assert "ok-app" not in md  # passing app is not listed by name


def test_report_marks_partial_run():
    run = _run()
    run["finished_at"] = None
    md = build_run_report_md(run, _results(), None)
    assert "Partial" in md


def test_report_all_passing():
    run = {
        "run_uid": "r",
        "mode": "ci",
        "total": 2,
        "passed": 2,
        "failed": 0,
        "finished_at": datetime(2026, 6, 10, tzinfo=UTC),
    }
    md = build_run_report_md(run, [{"id": 1, "status": "pass", "passed": True}], None)
    assert "None 🎉" in md
    assert "All 2 tests passed." in md


def test_rendered_html_does_not_leak_raw_markup():
    """
    Untrusted test output must not inject HTML when rendered (XSS guard).

    A code fence longer than any backtick run in the content prevents breakout,
    and markdown escapes content inside code blocks.
    """
    rows = [
        {
            "id": 9,
            "test_name": "evil",
            "app": "evil",
            "variant": "docker",
            "passed": False,
            "status": "fail",
            "classification": "app-crash",
            "headline": "```\n<script>alert(1)</script>\n```\n# not a heading",
            "error": None,
            "bundle_run_id": None,
        }
    ]
    md = build_run_report_md(_run(), rows, None)
    html_out = markdown.markdown(md, extensions=["fenced_code", "tables", "sane_lists"])
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out  # escaped instead


def _seed(db_path: Path) -> str:
    ResultStore(db_path=db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    uid = "2026-06-10T00-00-00Z-nightly-rep1"
    with Session(engine) as session:
        run = TestRun(
            run_uid=uid,
            mode="nightly",
            target_type="docker",
            target_name="t",
            total_tests=1,
            passed_tests=0,
            failed_tests=1,
            finished_at=datetime.now(UTC),
        )
        session.add(run)
        session.flush()
        session.add(
            TestResultRecord(
                run_id=run.id,
                test_name="apps/real-apps-docker/ghost",
                passed=False,
                status="fail",
                classification="build-failure",
                headline="x build-failure — ghost",
                duration=1.0,
                bundle_run_id="bundle-ghost",
            )
        )
        session.commit()
    return uid


def test_report_md_endpoint_serves_markdown(tmp_path):
    uid = _seed(tmp_path / "test-results.db")
    with TestClient(app=create_app()) as client:
        response = client.get(f"/runs/{uid}/report.md")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "# Run" in response.text
    assert "Build failures" in response.text


def test_run_detail_page_has_narrative_toggle(tmp_path):
    uid = _seed(tmp_path / "test-results.db")
    with TestClient(app=create_app()) as client:
        response = client.get(f"/runs/{uid}")
    assert response.status_code == 200
    assert ">Narrative<" in response.text
    assert 'id="report-md"' in response.text
    assert "Copy markdown" in response.text
