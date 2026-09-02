# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A failed dashboard mutation must not look like a successful one.

The regression: `app_restart`/`app_stop`/`app_backup` and
`backup_restore`/`backup_delete` caught every exception, sent it to the
server's stdout with `print()`, and returned the same redirect they return on
success. A failed **restore** — an operation whose entire purpose is getting
data back — was pixel-identical to a successful one in the UI and absent from
structured logs. That is the fake success the project's fail-loud rule
forbids.

These tests assert the *observable* contract: the redirect distinguishes the
two outcomes and carries the reason.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from litestar.testing import TestClient
from sqlalchemy.exc import IntegrityError

import hop3.config
from hop3.core.backup import BackupManager
from hop3.orm import App, get_session_factory
from hop3.orm.session import reset_session_factory_cache
from hop3.server.asgi import create_app


@pytest.fixture
def isolated_database(monkeypatch, worker_id, request):
    # A database named for *this test*, not the worker. The other dashboard
    # suites share one in-memory DB per worker, and a shared-cache SQLite DB
    # outlives a function-scoped fixture, so rows created here would leak into
    # a later file that asserts the app list is empty.
    slug = f"{worker_id}_{abs(hash(request.node.nodeid)) % 10**8}"
    db_uri = f"sqlite:///file:memdb_{slug}?mode=memory&cache=shared&uri=true"
    monkeypatch.setenv("HOP3_DATABASE_URI", db_uri)
    reset_session_factory_cache()
    get_session_factory()
    yield db_uri
    reset_session_factory_cache()


@pytest.fixture
def authenticated_client(isolated_database, monkeypatch):
    monkeypatch.setattr(hop3.config, "HOP3_UNSAFE", True)
    return TestClient(create_app())


@pytest.fixture
def an_app(isolated_database, request):
    # A distinct name per test: the shared-cache in-memory DB outlives the
    # function-scoped fixture, and app.name is unique (as it must be), so a
    # fixed name would collide on the second test in the same worker.
    name = f"app-{abs(hash(request.node.nodeid)) % 10**8}"
    factory = get_session_factory()
    with factory() as session:
        session.add(App(name=name))
        session.commit()
    return name


def _query_of(response) -> dict[str, list[str]]:
    return parse_qs(urlparse(response.headers["location"]).query)


def test_a_failing_restart_reports_failure_not_success(
    authenticated_client, an_app, monkeypatch
):
    def boom(self) -> None:
        msg = "uwsgi socket is gone"
        raise RuntimeError(msg)

    monkeypatch.setattr(App, "restart", boom)

    response = authenticated_client.post(
        f"/dashboard/apps/{an_app}/restart", follow_redirects=False
    )

    query = _query_of(response)
    assert query["success"] == ["false"], "a failed restart reported success"
    assert "uwsgi socket is gone" in query["error"][0]


def test_a_successful_restart_reports_success(
    authenticated_client, an_app, monkeypatch
):
    monkeypatch.setattr(App, "restart", lambda self: None)

    response = authenticated_client.post(
        f"/dashboard/apps/{an_app}/restart", follow_redirects=False
    )

    query = _query_of(response)
    assert query["success"] == ["true"]
    assert "error" not in query


def test_the_two_outcomes_are_distinguishable(
    authenticated_client, an_app, monkeypatch
):
    # The actual regression: these two used to produce identical responses.
    monkeypatch.setattr(App, "stop", lambda self: None)
    ok = authenticated_client.post(
        f"/dashboard/apps/{an_app}/stop", follow_redirects=False
    )

    def boom(self) -> None:
        msg = "nope"
        raise RuntimeError(msg)

    monkeypatch.setattr(App, "stop", boom)
    bad = authenticated_client.post(
        f"/dashboard/apps/{an_app}/stop", follow_redirects=False
    )

    assert ok.headers["location"] != bad.headers["location"]


def test_a_failing_backup_restore_reports_failure(authenticated_client, monkeypatch):
    def boom(self, backup_id, **kwargs):
        msg = "archive checksum mismatch"
        raise RuntimeError(msg)

    monkeypatch.setattr(BackupManager, "get_backup_info", boom)

    response = authenticated_client.post(
        "/dashboard/backups/20260101_000000_x/restore", follow_redirects=False
    )

    query = _query_of(response)
    assert query["success"] == ["false"], "a failed restore reported success"
    assert "archive checksum mismatch" in query["error"][0]


def test_two_apps_cannot_share_a_name(isolated_database):
    """
    The name is the app's identity, on disk and in every lookup.

    Before ``uq_app_name`` two rows could share one, and from then on
    ``get_app_or_none`` raised ``MultipleResultsFound`` for that name — the app
    became unreachable from both the CLI and the dashboard, with a 500 as the
    only symptom. This test found that bug by tripping over it.
    """
    factory = get_session_factory()
    with factory() as session:
        session.add(App(name="only-one"))
        session.commit()

    with pytest.raises(IntegrityError), factory() as session:
        session.add(App(name="only-one"))
        session.commit()
