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
two outcomes and carries the reason, in a signed flash the server issued, so a
crafted link cannot put its own words on the page.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from litestar.testing import TestClient
from sqlalchemy.exc import IntegrityError

from hop3.config import HopConfig
from hop3.core.backup import BackupManager
from hop3.orm import App, AppStateEnum, get_session_factory
from hop3.orm.session import reset_session_factory_cache
from hop3.server.asgi import create_app
from hop3.server.controllers.dashboard.helpers import flash_url, read_flash


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
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-dashboard-flash-0123")
    monkeypatch.setattr(HopConfig, "HOP3_UNSAFE", property(lambda _self: True))
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


def _flash_of(response) -> dict:
    """The outcome the redirect carries, as the next page will read it."""
    location = urlparse(response.headers["location"])
    flash = read_flash(parse_qs(location.query)["flash"][0], location.path)
    assert flash is not None, "the redirect carries no valid flash"
    return flash


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

    flash = _flash_of(response)
    assert not flash["ok"], "a failed restart reported success"
    assert "uwsgi socket is gone" in flash["text"]
    page = authenticated_client.get(response.headers["location"])
    assert "uwsgi socket is gone" in page.text


def test_a_successful_restart_reports_success(
    authenticated_client, an_app, monkeypatch
):
    monkeypatch.setattr(App, "restart", lambda self: None)

    response = authenticated_client.post(
        f"/dashboard/apps/{an_app}/restart", follow_redirects=False
    )

    flash = _flash_of(response)
    assert flash["ok"]
    assert "restarting" in flash["text"]


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

    assert _flash_of(ok)["ok"] != _flash_of(bad)["ok"]


def test_a_failing_backup_restore_reports_failure(authenticated_client, monkeypatch):
    def boom(self, backup_id, **kwargs):
        msg = "archive checksum mismatch"
        raise RuntimeError(msg)

    monkeypatch.setattr(BackupManager, "get_backup_info", boom)

    response = authenticated_client.post(
        "/dashboard/backups/20260101_000000_x/restore", follow_redirects=False
    )

    flash = _flash_of(response)
    assert not flash["ok"], "a failed restore reported success"
    assert "archive checksum mismatch" in flash["text"]
    page = authenticated_client.get(response.headers["location"])
    assert "archive checksum mismatch" in page.text


@pytest.mark.parametrize(
    "page", ["/dashboard/apps/{app}", "/dashboard/backups"], ids=["app", "backups"]
)
def test_a_crafted_link_cannot_put_text_on_the_page(authenticated_client, an_app, page):
    """The old banners printed `?error=` and `?message=` verbatim."""
    bait = "Your session expired, sign in again at evil.example"
    path = page.format(app=an_app)
    query = f"action=restore&success=false&error={bait}&message={bait}"

    response = authenticated_client.get(f"{path}?{query}&flash={bait}")

    assert response.status_code == 200
    assert "evil.example" not in response.text


def test_a_flash_for_another_page_is_not_shown(authenticated_client, an_app):
    """A genuine flash cannot be transplanted onto a page it was not issued for."""
    other = flash_url("/dashboard/backups", ok=False, text="genuine elsewhere")
    query = urlparse(other).query

    response = authenticated_client.get(f"/dashboard/apps/{an_app}?{query}")

    assert "genuine elsewhere" not in response.text


def test_polling_the_status_does_not_probe_or_write(
    authenticated_client, an_app, monkeypatch
):
    """
    ``GET .../status`` is a read (HTMX polls it every 5 s on every open page).

    It used to run ``sync_state()`` and commit, a mutation on a GET that also
    answered 500 for an app no deployer accepts.
    """
    factory = get_session_factory()
    with factory() as session:
        app = session.query(App).filter_by(name=an_app).one()
        app.run_state = AppStateEnum.RUNNING
        session.commit()

    def probe(self) -> None:
        msg = "no deployer accepts this app"
        raise RuntimeError(msg)

    monkeypatch.setattr(App, "sync_state", probe)

    response = authenticated_client.get(f"/dashboard/apps/{an_app}/status")

    assert response.status_code == 200
    assert 'data-state="RUNNING"' in response.text


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
