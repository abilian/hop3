# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Bundle drill-down: section reader (pure) + the bundle page."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_testing.results import ResultStore
from hop3_testing.results.models import TestResultRecord, TestRun
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hop3_testlab.bundles import read_bundle_sections
from hop3_testlab.web.asgi import create_app

if TYPE_CHECKING:
    from pathlib import Path


def test_read_bundle_sections_skips_placeholders_and_missing(tmp_path: Path):
    (tmp_path / "proxy_probe.txt").write_text("(not collected)")
    (tmp_path / "nginx.txt").write_text("connect() failed (111)")
    (tmp_path / "app.txt").write_text("listening on :8001")
    # journal.txt etc. are absent

    sections = read_bundle_sections(tmp_path)

    # Canonical order (nginx before app); placeholder + missing skipped.
    assert [name for name, _ in sections] == ["nginx", "app"]
    assert dict(sections)["nginx"].startswith("connect() failed")


def _seed_bundle(db_path: Path, bundle_run_id: str, bundle_dir: Path) -> None:
    ResultStore(db_path=db_path)  # ensure schema
    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        run = TestRun(
            run_uid="run-1",
            mode="nightly",
            target_type="docker",
            target_name="hetzner-1",
            total_tests=1,
            passed_tests=0,
            failed_tests=1,
        )
        session.add(run)
        session.flush()
        session.add(
            TestResultRecord(
                run_id=run.id,
                test_name="focalboard",
                passed=False,
                status="fail",
                classification="proxy-502",
                headline="x proxy-502 - focalboard",
                bundle_run_id=bundle_run_id,
                bundle_path=str(bundle_dir),
            )
        )
        session.commit()


def test_bundle_page_renders_sections(tmp_path: Path):
    db = tmp_path / "test-results.db"  # conftest set TESTLAB_DB_PATH here
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "nginx.txt").write_text(
        "connect() failed (111: Connection refused) upstream 127.0.0.1:8000"
    )
    (bundle_dir / "proxy_probe.txt").write_text("(not collected)")
    bundle_run_id = "2026-06-06T00-00-00Z-focalboard-abc"
    _seed_bundle(db, bundle_run_id, bundle_dir)

    with TestClient(app=create_app()) as client:
        response = client.get(f"/bundle/{bundle_run_id}")

    assert response.status_code == 200
    assert "nginx" in response.text
    assert "Connection refused" in response.text


def test_bundle_unknown_is_404(tmp_path: Path):
    with TestClient(app=create_app()) as client:
        response = client.get("/bundle/does-not-exist")
    assert response.status_code == 404
