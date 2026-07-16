# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `hop3 catalog install` — validation/error paths.

Every case here refuses BEFORE App.create() runs (unavailable catalog, unknown
blueprint, bad/duplicate name, missing --app / blueprint-id), so no filesystem
root is needed. The on-disk happy path lives in the b_integration suite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.commands.catalog import CatalogInstallCmd, _parse_install_rest
from hop3.server.catalog import service as service_module
from hop3.server.catalog.service import CatalogService

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _reset_catalog_singleton():
    CatalogService.reset()
    yield
    CatalogService.reset()


def _write_catalog(tmp_path: Path, app_id: str = "nextcloud") -> Path:
    cat = tmp_path / "catalog"
    app_dir = cat / app_id
    app_dir.mkdir(parents=True)
    (app_dir / "hop3.toml").write_text(
        f'[metadata]\nid = "{app_id}"\ntitle = "{app_id}"\n'
    )
    return cat


@pytest.fixture
def loaded_catalog(tmp_path, monkeypatch) -> Path:
    cat = _write_catalog(tmp_path)
    monkeypatch.setattr(service_module, "_default_catalog_dir", lambda: cat)
    CatalogService.get_instance().load(cat)
    return cat


def _texts(result: list[dict]) -> str:
    return " ".join(r.get("text", "") for r in result)


def _is_error(result: list[dict]) -> bool:
    return any(r.get("t") == "error" for r in result)


def test_install_requires_blueprint_id(db_session: Session, loaded_catalog) -> None:
    result = CatalogInstallCmd(db_session=db_session).call("--app", "myapp")
    assert _is_error(result)


def test_install_rejects_extra_arguments(db_session: Session, loaded_catalog) -> None:
    result = CatalogInstallCmd(db_session=db_session).call(
        "nextcloud", "extra", "--app", "myapp"
    )
    assert _is_error(result)
    assert "extra" in _texts(result)


def test_install_unknown_catalog_id(db_session: Session, loaded_catalog) -> None:
    result = CatalogInstallCmd(db_session=db_session).call("ghost", "--app", "myapp")
    assert _is_error(result)
    assert "ghost" in _texts(result)


def test_install_invalid_app_name(db_session: Session, loaded_catalog) -> None:
    result = CatalogInstallCmd(db_session=db_session).call("nextcloud", "--app", "A B")
    assert _is_error(result)


def test_install_duplicate_app_name(
    db_session: Session, test_app, loaded_catalog
) -> None:
    # test_app is named "testapp" and already committed.
    result = CatalogInstallCmd(db_session=db_session).call(
        "nextcloud", "--app", "testapp"
    )
    assert _is_error(result)
    assert "already exists" in _texts(result).lower()


def test_install_no_catalog_published(
    db_session: Session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        service_module, "_default_catalog_dir", lambda: tmp_path / "nope"
    )
    result = CatalogInstallCmd(db_session=db_session).call(
        "nextcloud", "--app", "myapp"
    )
    assert _is_error(result)


# --- argument parsing (pure) ---------------------------------------------


def test_parse_install_rest_defaults() -> None:
    app_id, env_lines, extras, domain = _parse_install_rest(["nextcloud"])
    assert (app_id, env_lines, extras, domain) == ("nextcloud", [], [], None)


def test_parse_install_rest_domain_space_and_short_and_equals() -> None:
    for tokens in (
        ["nextcloud", "--domain", "cloud.example.com"],
        ["nextcloud", "-d", "cloud.example.com"],
        ["nextcloud", "--domain=cloud.example.com"],
    ):
        app_id, _env, extras, domain = _parse_install_rest(tokens)
        assert app_id == "nextcloud"
        assert domain == "cloud.example.com"
        assert extras == []


def test_parse_install_rest_domain_with_env() -> None:
    app_id, env_lines, extras, domain = _parse_install_rest([
        "nextcloud",
        "--env",
        "FOO=bar",
        "--domain",
        "cloud.example.com",
    ])
    assert app_id == "nextcloud"
    assert env_lines == ["FOO=bar"]
    assert domain == "cloud.example.com"
    assert extras == []
