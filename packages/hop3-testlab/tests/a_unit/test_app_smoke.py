# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests: the app builds, DI injection works, templates render."""

from __future__ import annotations

from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient


def test_health_returns_ok():
    with TestClient(app=create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_index_renders_when_empty():
    # The decided DI path end-to-end: @inject + FromDishka[RunsRepository]
    # resolves, the read session opens over an (empty) store, the template renders.
    with TestClient(app=create_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Hop3 Test Lab" in response.text
    assert "No runs yet" in response.text


def test_dashboard_trigger_form_offers_coverage_mode():
    # The trigger form's mode dropdown must include the "coverage" profile
    # (regression: it was missing from the hardcoded list in the controller).
    with TestClient(app=create_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert 'name="mode"' in response.text  # the dropdown exists
    assert 'value="coverage"' in response.text  # ...and offers coverage


def test_dashboard_lists_recent_runs(tmp_path):
    # One store, two front-ends: a run written via the CLI's ResultStore shows up
    # on the web dashboard. (conftest points TESTLAB_DB_PATH at this tmp DB.)
    from hop3_testing.results import ResultStore  # noqa: PLC0415

    store = ResultStore(db_path=tmp_path / "test-results.db")
    run = store.start_run(mode="nightly", target_type="docker", target_name="hetzner-1")
    store.finish_run()

    with TestClient(app=create_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert run.run_uid in response.text
    assert "hetzner-1" in response.text  # target column


def test_dashboard_skips_legacy_runs_without_uid(tmp_path):
    # A pre-ADR-044 row with no run_uid can't link to a detail page, so it's
    # omitted from the dashboard (rather than rendering a broken /runs/None link).
    from hop3_testing.results import ResultStore  # noqa: PLC0415
    from hop3_testing.results.models import TestRun  # noqa: PLC0415
    from sqlalchemy import create_engine  # noqa: PLC0415
    from sqlalchemy.orm import Session  # noqa: PLC0415

    db = tmp_path / "test-results.db"
    ResultStore(db_path=db)
    engine = create_engine(f"sqlite:///{db}")
    with Session(engine) as s:
        s.add(TestRun(run_uid=None, mode="nightly", target_type="docker"))
        s.commit()

    with TestClient(app=create_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "No runs yet" in response.text  # the null-uid row is not listed
