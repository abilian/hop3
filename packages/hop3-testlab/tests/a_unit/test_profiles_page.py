# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The /profiles page lists and edits test-execution modes from the UI."""

from __future__ import annotations

import pytest
from hop3_testing.selector import get_mode_config, list_modes
from hop3_testlab.web.asgi import create_app
from litestar.testing import TestClient


@pytest.fixture(autouse=True)
def _isolated_modes_file(tmp_path, monkeypatch):
    """Never touch the developer's ~/.hop3/test-modes.toml."""
    monkeypatch.setenv("HOP3_TEST_MODES", str(tmp_path / "test-modes.toml"))


def test_profiles_page_lists_builtin_modes():
    with TestClient(app=create_app()) as client:
        response = client.get("/profiles")
    assert response.status_code == 200
    for name in ("dev", "ci", "coverage", "nightly", "release"):
        assert name in response.text


def test_save_overrides_a_builtin_mode():
    with TestClient(app=create_app()) as client:
        response = client.post(
            "/profiles/save",
            data={
                "name": "ci",
                "tiers": ["fast"],  # dropped "medium"
                "priorities": ["P0"],
                "targets": ["docker"],
                "description": "CI, fast only",
                "max_duration_minutes": "10",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert get_mode_config("ci").tiers == ["fast"]


def test_add_and_delete_custom_profile():
    with TestClient(app=create_app()) as client:
        client.post(
            "/profiles/save",
            data={
                "name": "smoke",
                "tiers": ["fast"],
                "priorities": ["P0"],
                "targets": ["docker"],
                "description": "smoke",
            },
            follow_redirects=False,
        )
        assert "smoke" in list_modes()

        client.post("/profiles/delete", data={"name": "smoke"}, follow_redirects=False)
        assert "smoke" not in list_modes()


def test_reset_builtin_restores_default():
    with TestClient(app=create_app()) as client:
        client.post(
            "/profiles/save",
            data={
                "name": "ci",
                "tiers": ["fast"],
                "priorities": ["P0"],
                "targets": ["docker"],
            },
            follow_redirects=False,
        )
        assert get_mode_config("ci").tiers == ["fast"]

        client.post("/profiles/reset", data={"name": "ci"}, follow_redirects=False)
        assert get_mode_config("ci").tiers == ["fast", "medium"]


def test_invalid_target_is_rejected():
    with TestClient(app=create_app()) as client:
        response = client.post(
            "/profiles/save",
            data={
                "name": "ci",
                "tiers": ["fast"],
                "priorities": ["P0"],
                "targets": ["bogus"],  # not a valid target
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/profiles?msg=invalid"
    # The bad edit was not persisted: ci keeps its built-in targets.
    assert get_mode_config("ci").targets == ["docker"]


def test_builtin_cannot_be_deleted_via_ui():
    with TestClient(app=create_app()) as client:
        response = client.post(
            "/profiles/delete", data={"name": "ci"}, follow_redirects=False
        )
    assert response.headers["location"] == "/profiles?msg=protected"
    assert "ci" in list_modes()
