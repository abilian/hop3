# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The backups page pages through every backup and says how many there are.

It used to list the 100 most recent with no total and no way further, so the
101st backup was invisible from the dashboard.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest
from litestar.testing import TestClient

from hop3.config import HopConfig
from hop3.core.backup import BackupManifest
from hop3.orm import App, Backup, get_session_factory
from hop3.orm.session import reset_session_factory_cache
from hop3.server.asgi import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOP3_DATABASE_URI", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-key-for-backup-paging-012345")
    monkeypatch.setattr(HopConfig, "HOP3_UNSAFE", property(lambda _self: True))
    reset_session_factory_cache()
    yield TestClient(create_app())
    reset_session_factory_cache()


@pytest.fixture
def five_backups(client, tmp_path) -> list[str]:
    """Five backups of one app, oldest first, each with its manifest on disk."""
    ids = [f"2026010{i}_120000_ab" for i in range(1, 6)]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with get_session_factory()() as session:
        app = App(name="paged")
        session.add(app)
        session.flush()
        for n, backup_id in enumerate(ids):
            path = tmp_path / "backups" / backup_id
            path.mkdir(parents=True)
            manifest = BackupManifest(
                backup_id=backup_id,
                app_name="paged",
                created_at=start.isoformat(),
                format_version="1",
                hop3_version="0",
                size_bytes=1,
                checksums={},
                app_metadata={},
                addons=[],
                env_vars_count=0,
                expires_after=0,
            )
            (path / "metadata.json").write_text(json.dumps(asdict(manifest)))
            backup = Backup(app_id=app.id, remote_path=str(path))
            backup.created_at = start + timedelta(days=n)
            session.add(backup)
        session.commit()
    return ids


def test_a_page_shows_its_range_and_the_total(client, five_backups) -> None:
    page = client.get("/dashboard/backups?offset=2&limit=2")

    assert page.status_code == 200
    assert "Showing 3–4 of 5" in page.text
    # Most recent first: the 3rd and 4th newest, and nothing else.
    newest_first = five_backups[::-1]
    assert newest_first[2] in page.text
    assert newest_first[3] in page.text
    assert newest_first[0] not in page.text
    assert newest_first[4] not in page.text
    assert "offset=0&amp;limit=2" in page.text  # previous
    assert "offset=4&amp;limit=2" in page.text  # next


def test_the_last_page_has_no_next(client, five_backups) -> None:
    page = client.get("/dashboard/backups?offset=4&limit=2")

    assert "Showing 5–5 of 5" in page.text
    assert "offset=6" not in page.text


def test_an_unreadable_backup_is_listed_with_its_reason(
    client, five_backups, tmp_path
) -> None:
    """
    A backup whose manifest is gone used to be skipped with a log line, so the
    page showed fewer rows than its counts and the broken backup nowhere.
    """
    broken = five_backups[-1]  # the newest, so it is on the first page
    (tmp_path / "backups" / broken / "metadata.json").unlink()

    page = client.get("/dashboard/backups?offset=0&limit=5")

    assert "Showing 1–5 of 5" in page.text
    assert broken in page.text
    assert "Unreadable:" in page.text
    assert "no manifest at" in page.text
    # No Restore or Info for it: there is nothing to restore from.
    assert f"/dashboard/backups/{broken}/restore" not in page.text
    assert f"/dashboard/backups/{broken}/delete" in page.text
