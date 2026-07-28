# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Integration tests for the wired dashboard catalog-install form.

The install POST now stages the recipe (shared with the CLI) AND kicks off the
background deploy — so we stub ``deploy_app_streaming`` (no real build) and
assert the app is staged, the deploy is triggered, and the redirect no longer
claims premature success.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from litestar.testing import TestClient

import hop3.config
from hop3.config import HopConfig
from hop3.orm import App, reset_session_factory_cache
from hop3.server.asgi import create_app
from hop3.server.catalog import service as service_module
from hop3.server.catalog.service import CatalogService
from hop3.server.lib.database import get_session

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def setup_secret_key():
    os.environ["HOP3_SECRET_KEY"] = "test-secret-key-for-integration-testing"
    yield
    os.environ.pop("HOP3_SECRET_KEY", None)


@pytest.fixture
def deploy_calls(monkeypatch) -> list[tuple[str, int]]:
    """Stub the background deploy so no real build/thread is started."""
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "hop3.server.controllers.catalog.deploy_app_streaming",
        lambda name, pk: calls.append((name, pk)) or {"t": "stream", "stream_id": "x"},
    )
    return calls


@pytest.fixture
def test_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOP3_DATABASE_URI", f"sqlite:///{tmp_path}/test.db")
    HopConfig.reset_instance()
    reset_session_factory_cache()
    HopConfig.set_instance(HopConfig(hop3_root=tmp_path))
    (tmp_path / "apps").mkdir(exist_ok=True)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)

    cat = tmp_path / "catalog"
    app_dir = cat / "nextcloud"
    app_dir.mkdir(parents=True)
    (app_dir / "hop3.toml").write_text(
        '[metadata]\nid = "nextcloud"\ntitle = "Nextcloud"\n'
    )
    monkeypatch.setattr(service_module, "_default_catalog_dir", lambda: cat)
    CatalogService.reset()
    CatalogService.get_instance().load(cat)

    monkeypatch.setattr(hop3.config, "HOP3_UNSAFE", True)  # bypass auth_guard
    client = TestClient(create_app())
    yield client

    HopConfig.reset_instance()
    reset_session_factory_cache()
    CatalogService.reset()


def test_install_stages_and_deploys(test_client, deploy_calls, tmp_path) -> None:
    resp = test_client.post(
        "/dashboard/catalog/apps/nextcloud/install",
        data={"app_name": "mycloud", "env_vars": "FOO=bar"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    # No optimistic "installed=true": the redirect reflects a deploy in progress.
    location = resp.headers["location"]
    assert location.startswith("/dashboard/apps/mycloud")
    assert "installed=true" not in location

    with get_session() as s:
        assert s.query(App).filter_by(name="mycloud").first() is not None
    assert (tmp_path / "apps" / "mycloud" / "src" / "hop3.toml").exists()
    assert len(deploy_calls) == 1
    assert deploy_calls[0][0] == "mycloud"


def test_install_unknown_id_redirects_to_catalog(test_client, deploy_calls) -> None:
    resp = test_client.post(
        "/dashboard/catalog/apps/ghost/install",
        data={"app_name": "whatever"},
        follow_redirects=False,
    )
    assert resp.status_code in {302, 303}
    assert resp.headers["location"] == "/dashboard/catalog"
    assert deploy_calls == []


def test_install_invalid_name_rerenders_form(test_client, deploy_calls) -> None:
    resp = test_client.post(
        "/dashboard/catalog/apps/nextcloud/install",
        data={"app_name": "A B"},
    )
    assert resp.status_code == 200  # detail page re-rendered with errors
    assert b"must" in resp.content.lower()
    assert deploy_calls == []


def test_install_form_defaults_the_name_to_the_blueprint_id(test_client) -> None:
    """
    The name field arrives pre-filled with the blueprint's own id.

    Matches `hop3 catalog install <id>`, which names the app after the blueprint
    unless --app overrides it, so the web and CLI agree on the default instead
    of the form starting empty.
    """
    resp = test_client.get("/dashboard/catalog/apps/nextcloud")

    assert resp.status_code == 200
    content = resp.content.decode("utf-8", errors="ignore")
    assert 'id="app_name"' in content
    assert 'value="nextcloud"' in content


def test_install_form_keeps_a_rejected_name_rather_than_resetting(
    test_client, deploy_calls
) -> None:
    """A validation error must not discard what the operator typed."""
    resp = test_client.post(
        "/dashboard/catalog/apps/nextcloud/install",
        data={"app_name": "my-cloud!"},
    )

    assert resp.status_code == 200
    content = resp.content.decode("utf-8", errors="ignore")
    assert 'value="my-cloud!"' in content
    assert deploy_calls == []
