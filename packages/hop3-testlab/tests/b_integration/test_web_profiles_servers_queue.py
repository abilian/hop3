# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The Phase-4 UI: server pool CRUD, build profiles, Start build → queue.

Drives the real Litestar app (auth bypassed via TESTLAB_UNSAFE in the conftest)
against the real SQLite store.
"""

from __future__ import annotations

from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import (
    BuildQueueRepository,
    ProfilesRepository,
    ServersRepository,
)
from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient


def _session():
    return get_session_factory(str(TestlabConfig.get_instance().DB_PATH))()


def test_server_pool_crud_via_ui():
    with TestClient(app=create_app()) as client:
        r = client.post(
            "/servers",
            data={"name": "docker-local", "target_id": "docker", "kind": "docker"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "docker-local" in client.get("/servers").text

    with _session() as s:
        row = ServersRepository(s).list_all()[0]
        sid = row.id
        assert row.target_id == "docker"
        assert row.enabled is True

    with TestClient(app=create_app()) as client:
        client.post(f"/servers/{sid}/toggle", follow_redirects=False)
    with _session() as s:
        assert ServersRepository(s).get(sid).enabled is False  # toggled off

    with TestClient(app=create_app()) as client:
        client.post(f"/servers/{sid}/delete", follow_redirects=False)
    with _session() as s:
        assert ServersRepository(s).get(sid) is None


def test_profile_create_maps_form_to_rules():
    with TestClient(app=create_app()) as client:
        r = client.post(
            "/profiles",
            data={
                "name": "nightly",
                "source_name": "main-repo",
                "source_url": "https://example.com/hop3.git",
                "source_ref": "devel",
                "platform_ref": "main",
                "mode": "smoke",
                "types": "app, demo",
                "priorities": "P0",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "nightly" in client.get("/profiles").text

    with _session() as s:
        p = ProfilesRepository(s).list_all()[0]
        assert p.source_ref == "devel"
        assert p.platform_ref == "main"
        # The form's mode + comma lists became a rule dict (never an app list).
        assert p.selection == {
            "mode": "smoke",
            "types": ["app", "demo"],
            "priorities": ["P0"],
        }


def test_start_build_enqueues_and_shows_in_queue():
    with _session() as s:
        p = ProfilesRepository(s).create(
            name="p1",
            source_name="main-repo",
            source_url="u",
            source_ref="main",
            selection={"mode": "smoke"},
        )
        s.commit()
        pid = p.id

    with TestClient(app=create_app()) as client:
        r = client.post(f"/profiles/{pid}/start", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/queue")
        assert "p1" in client.get("/queue").text  # the queued build is listed

    with _session() as s:
        reqs = BuildQueueRepository(s).list_recent()
        assert len(reqs) == 1
        assert reqs[0].profile_id == pid
        assert reqs[0].status == "pending"
        assert reqs[0].actor == "web"


def test_queue_shows_build_number_and_folds_the_detail():
    """The queue lists the build number and keeps the (long) failure reason in a
    folded <details> so it doesn't blow out the row."""
    with _session() as s:
        p = ProfilesRepository(s).create(
            name="p-fail",
            source_name="m",
            source_url="u",
            source_ref="main",
            selection={"mode": "smoke"},
        )
        s.commit()
        bq = BuildQueueRepository(s)
        req_id = bq.enqueue(p.id).id
        s.commit()
        bq.mark(req_id, "failed", detail="hop3-deploy failed: boom")
        s.commit()

    with TestClient(app=create_app()) as client:
        page = client.get("/queue").text

    assert f"#{req_id}" in page  # build number column
    assert "hop3-deploy failed: boom" in page  # the reason is present...
    assert "<details>" in page  # ...inside a foldable section
    assert "<details open" not in page  # folded by default


def test_queue_cancel_pending_build():
    with _session() as s:
        p = ProfilesRepository(s).create(
            name="p", source_name="m", source_url="u", source_ref="main", selection={}
        )
        s.commit()
        req_id = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()

    with TestClient(app=create_app()) as client:
        client.post(f"/queue/{req_id}/cancel", follow_redirects=False)

    with _session() as s:
        assert BuildQueueRepository(s).get(req_id).status == "cancelled"


def test_management_forms_carry_csrf_token():
    """Every management POST form embeds the CSRF token (else 403 in production)."""
    with _session() as s:
        p = ProfilesRepository(s).create(
            name="p",
            source_name="m",
            source_url="https://example.com/r.git",
            source_ref="main",
            selection={},
        )
        ServersRepository(s).create(name="srv", target_id="docker", kind="docker")
        BuildQueueRepository(s).enqueue(p.id)  # a pending build -> cancel form renders
        s.commit()

    with TestClient(app=create_app()) as client:
        for path in ("/profiles", "/servers", "/queue"):
            assert 'name="_csrf_token"' in client.get(path).text, f"{path} lacks CSRF"


def test_profile_create_rejects_unsafe_source_url():
    """A git transport-helper URL is refused (400), not stored."""
    with TestClient(app=create_app()) as client:
        r = client.post(
            "/profiles",
            data={"name": "bad", "source_url": "ext::sh -c evil", "source_ref": "main"},
            follow_redirects=False,
        )
        assert r.status_code == 400  # ValidationException
    with _session() as s:
        assert ProfilesRepository(s).list_all() == []  # nothing created


def test_queue_log_view_renders_the_engine_log():
    """A build's engine log is fetched from disk and shown in the UI — not left as a
    'diagnostics saved to <path>' pointer the user can't reach."""
    with _session() as s:
        p = ProfilesRepository(s).create(
            name="p-log",
            source_name="m",
            source_url="u",
            source_ref="main",
            selection={},
        )
        rid = BuildQueueRepository(s).enqueue(p.id).id
        BuildQueueRepository(s).mark(rid, "failed", detail="setup failed")
        s.commit()

    # The worker writes the engine log under DATA_DIR/logs (conftest isolates -> tmp).
    logs = TestlabConfig.get_instance().DATA_DIR / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"build-{rid}-20260101T000000Z.log").write_text(
        "ENGINE OUTPUT\n✗ Failed to setup deployment target\n"
        "Host key verification failed.\n"
    )

    with TestClient(app=create_app()) as client:
        page = client.get(f"/queue/{rid}/log").text
        assert "Host key verification failed." in page  # the full log, in the UI
        assert f"/queue/{rid}/log" in client.get("/queue").text  # listing links to it


def test_queue_log_view_handles_missing_log():
    with _session() as s:
        p = ProfilesRepository(s).create(
            name="p-nolog",
            source_name="m",
            source_url="u",
            source_ref="main",
            selection={},
        )
        rid = BuildQueueRepository(s).enqueue(p.id).id
        s.commit()
    with TestClient(app=create_app()) as client:
        r = client.get(f"/queue/{rid}/log")
    assert r.status_code == 200
    assert "No engine log" in r.text
