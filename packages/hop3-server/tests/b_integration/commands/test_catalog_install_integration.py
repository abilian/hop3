# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Integration test for `hop3 catalog install` — the on-disk happy path.

Creates a real App under a tmp HOP3 root and asserts the recipe is staged, then
that the deploy is triggered with (app_name, app.id). ``deploy_app_streaming`` is
stubbed so no real build/run (or background thread) is started.
"""

from __future__ import annotations

import pytest

from hop3.commands.catalog import CatalogInstallCmd
from hop3.config import HopConfig
from hop3.orm import App, get_session_factory, reset_session_factory_cache
from hop3.server.catalog import service as service_module
from hop3.server.catalog.service import CatalogService


@pytest.fixture
def rooted(tmp_path, monkeypatch):
    monkeypatch.setenv("HOP3_DATABASE_URI", f"sqlite:///{tmp_path}/test.db")
    HopConfig.reset_instance()
    reset_session_factory_cache()
    HopConfig.set_instance(HopConfig(hop3_root=tmp_path))
    (tmp_path / "apps").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()

    cat = tmp_path / "catalog"
    app_dir = cat / "nextcloud"
    app_dir.mkdir(parents=True)
    (app_dir / "hop3.toml").write_text(
        '[metadata]\nid = "nextcloud"\ntitle = "Nextcloud"\n'
    )
    (app_dir / "Procfile").write_text("web: true\n")
    monkeypatch.setattr(service_module, "_default_catalog_dir", lambda: cat)
    CatalogService.reset()
    CatalogService.get_instance().load(cat)

    yield tmp_path

    HopConfig.reset_instance()
    reset_session_factory_cache()
    CatalogService.reset()


def test_install_stages_recipe_and_triggers_deploy(rooted, monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def _fake_deploy(app_name: str, app_id: int) -> dict:
        calls.append((app_name, app_id))
        return {"t": "stream", "stream_id": "test-stream"}

    monkeypatch.setattr("hop3.commands.catalog.deploy_app_streaming", _fake_deploy)

    session = get_session_factory()()
    result = CatalogInstallCmd(db_session=session).call(
        "nextcloud", "--app", "mycloud", "--env", "FOO=bar"
    )

    # The app was created and persisted, with the recipe staged into src/.
    app = session.query(App).filter_by(name="mycloud").first()
    assert app is not None
    assert (rooted / "apps" / "mycloud" / "src" / "hop3.toml").exists()
    env = {ev.name: ev.value for ev in app.env_vars}
    assert env.get("FOO") == "bar"

    # The deploy was triggered exactly once with (name, id); the response is the
    # single stream item that makes the CLI attach to the SSE log stream.
    assert calls == [("mycloud", app.id)]
    assert result == [{"t": "stream", "stream_id": "test-stream"}]


def test_install_defaults_app_name_to_blueprint_id(rooted, monkeypatch) -> None:
    """Without --app, the instance is named after the blueprint id."""
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hop3.commands.catalog.deploy_app_streaming",
        lambda app_name, app_id: (
            calls.append((app_name, app_id)) or {"t": "stream", "stream_id": "s"}
        ),
    )

    session = get_session_factory()()
    CatalogInstallCmd(db_session=session).call("nextcloud")  # no --app

    app = session.query(App).filter_by(name="nextcloud").first()
    assert app is not None
    assert calls == [("nextcloud", app.id)]
