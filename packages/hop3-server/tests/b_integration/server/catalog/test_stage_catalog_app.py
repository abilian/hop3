# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Integration tests for the shared catalog-install staging service.

``stage_catalog_app`` creates a real App on disk (under a tmp HOP3 root), copies
the blueprint recipe into it, and attaches env vars — but never deploys.
"""

from __future__ import annotations

import shutil
from types import SimpleNamespace

import pytest

from hop3.config import HopConfig
from hop3.orm import App, get_session_factory, reset_session_factory_cache
from hop3.server.catalog import install as install_module, service as service_module
from hop3.server.catalog.install import CatalogInstallError, stage_catalog_app
from hop3.server.catalog.service import CatalogService


@pytest.fixture
def rooted(tmp_path, monkeypatch):
    monkeypatch.setenv("HOP3_DATABASE_URI", f"sqlite:///{tmp_path}/test.db")
    HopConfig.reset_instance()
    reset_session_factory_cache()
    HopConfig.set_instance(HopConfig(hop3_root=tmp_path))
    (tmp_path / "apps").mkdir()

    cat = tmp_path / "catalog"
    app_dir = cat / "nextcloud"
    app_dir.mkdir(parents=True)
    (app_dir / "hop3.toml").write_text(
        '[metadata]\nid = "nextcloud"\ntitle = "Nextcloud"\n'
    )
    (app_dir / "readme.md").write_text("# Nextcloud\n")
    monkeypatch.setattr(service_module, "_default_catalog_dir", lambda: cat)
    CatalogService.reset()
    CatalogService.get_instance().load(cat)

    yield tmp_path

    HopConfig.reset_instance()
    reset_session_factory_cache()
    CatalogService.reset()


def test_stage_creates_app_copies_recipe_and_env(rooted) -> None:
    session = get_session_factory()()
    app = stage_catalog_app(
        "nextcloud", "MyCloud", "FOO=bar\n# comment\nBAZ=1\n", session
    )

    # name normalized to lowercase, persisted
    assert app.name == "mycloud"
    assert session.query(App).filter_by(name="mycloud").first() is not None

    # recipe copied into the app's source tree (hop3.toml + sibling)
    src = rooted / "apps" / "mycloud" / "src"
    assert (src / "hop3.toml").is_file()
    assert (src / "readme.md").is_file()

    # env vars parsed (comment + blank skipped)
    env = {ev.name: ev.value for ev in app.env_vars}
    assert env == {"FOO": "bar", "BAZ": "1"}


def test_stage_rejects_unknown_blueprint(rooted) -> None:
    session = get_session_factory()()
    with pytest.raises(CatalogInstallError, match="ghost"):
        stage_catalog_app("ghost", "myapp", "", session)


def test_stage_rejects_when_recipe_dir_is_gone(rooted, monkeypatch) -> None:
    # Loaded into the catalog, but the on-disk recipe vanished before install:
    # must fail loud, not stage an empty (undeployable) app.
    session = get_session_factory()()
    shutil.rmtree(rooted / "catalog" / "nextcloud")
    with pytest.raises(CatalogInstallError, match="no recipe"):
        stage_catalog_app("nextcloud", "myapp", "", session)
    assert session.query(App).filter_by(name="myapp").first() is None
    assert not (rooted / "apps" / "myapp").exists()


def test_stage_rejects_duplicate_name(rooted) -> None:
    session = get_session_factory()()
    stage_catalog_app("nextcloud", "mycloud", "", session)
    with pytest.raises(CatalogInstallError, match="already exists"):
        stage_catalog_app("nextcloud", "mycloud", "", session)


# --- hostname auto-assignment (streamlined, one-command reachable install) ---


@pytest.fixture
def admin_domain(monkeypatch):
    """Give install.py a fixed ADMIN_DOMAIN, independent of server config."""
    monkeypatch.setattr(
        install_module, "config", SimpleNamespace(ADMIN_DOMAIN="apps.example.com")
    )


def _host_name(app: App) -> str | None:
    return next((ev.value for ev in app.env_vars if ev.name == "HOST_NAME"), None)


def test_stage_auto_assigns_hostname_from_admin_domain(rooted, admin_domain) -> None:
    session = get_session_factory()()
    app = stage_catalog_app("nextcloud", "wiki", "", session)
    assert _host_name(app) == "wiki.apps.example.com"


def test_stage_uses_explicit_domain_over_admin_domain(rooted, admin_domain) -> None:
    session = get_session_factory()()
    app = stage_catalog_app(
        "nextcloud", "wiki", "", session, domain="cloud.example.com"
    )
    assert _host_name(app) == "cloud.example.com"


def test_stage_keeps_explicit_host_name_env(rooted, admin_domain) -> None:
    # A user-provided --env HOST_NAME wins over the auto-assigned default.
    session = get_session_factory()()
    app = stage_catalog_app(
        "nextcloud", "wiki", "HOST_NAME=custom.example.com", session
    )
    assert _host_name(app) == "custom.example.com"


def test_stage_no_admin_domain_stays_loopback(rooted, monkeypatch) -> None:
    # No domain and no ADMIN_DOMAIN -> no HOST_NAME (unchanged loopback-only).
    monkeypatch.setattr(install_module, "config", SimpleNamespace(ADMIN_DOMAIN=""))
    session = get_session_factory()()
    app = stage_catalog_app("nextcloud", "wiki", "", session)
    assert _host_name(app) is None


def test_stage_rejects_hostname_conflict(rooted, admin_domain) -> None:
    # Another app already owns the host the default would assign -> fail loud.
    session = get_session_factory()()
    stage_catalog_app("nextcloud", "other", "HOST_NAME=wiki.apps.example.com", session)
    with pytest.raises(CatalogInstallError, match="already in use"):
        stage_catalog_app("nextcloud", "wiki", "", session)


def test_stage_rejects_invalid_domain(rooted) -> None:
    session = get_session_factory()()
    with pytest.raises(CatalogInstallError, match="Invalid hostname"):
        stage_catalog_app("nextcloud", "wiki", "", session, domain="not a host!")


def test_stage_recipe_pinned_domain_is_not_overridden(rooted, admin_domain) -> None:
    # A recipe that declares its own [domains] keeps it: no HOST_NAME is staged,
    # so the recipe's [domains] drives the vhost at deploy time.
    recipe = rooted / "catalog" / "nextcloud" / "hop3.toml"
    recipe.write_text(
        '[metadata]\nid = "nextcloud"\n[domains]\nlist = ["pinned.example.com"]\n'
    )
    session = get_session_factory()()
    app = stage_catalog_app("nextcloud", "wiki", "", session)
    assert _host_name(app) is None


def test_stage_explicit_domain_overrides_recipe_pin(rooted, admin_domain) -> None:
    # An explicit --domain is more specific than the recipe's own [domains].
    recipe = rooted / "catalog" / "nextcloud" / "hop3.toml"
    recipe.write_text(
        '[metadata]\nid = "nextcloud"\n[domains]\nlist = ["pinned.example.com"]\n'
    )
    session = get_session_factory()()
    app = stage_catalog_app(
        "nextcloud", "wiki", "", session, domain="chosen.example.com"
    )
    assert _host_name(app) == "chosen.example.com"


def test_stage_rejects_conflicting_env_host_name(rooted, admin_domain) -> None:
    # A --env HOST_NAME colliding with another app is refused too (not just the
    # auto/-domain path) — the explicit-env branch is validated, not trusted.
    session = get_session_factory()()
    stage_catalog_app("nextcloud", "other", "HOST_NAME=shared.example.com", session)
    with pytest.raises(CatalogInstallError, match="already in use"):
        stage_catalog_app("nextcloud", "wiki", "HOST_NAME=shared.example.com", session)


def test_stage_rejects_invalid_env_host_name(rooted, admin_domain) -> None:
    session = get_session_factory()()
    with pytest.raises(CatalogInstallError, match="Invalid hostname"):
        stage_catalog_app("nextcloud", "wiki", "HOST_NAME=not a host!", session)


def test_stage_env_host_name_wins_over_domain(rooted, admin_domain) -> None:
    # Both supplied: the explicit --env HOST_NAME is the most specific and wins.
    session = get_session_factory()()
    app = stage_catalog_app(
        "nextcloud",
        "wiki",
        "HOST_NAME=env.example.com",
        session,
        domain="d.example.com",
    )
    assert _host_name(app) == "env.example.com"


def test_stage_rejects_admin_domain_as_domain(
    rooted, admin_domain, monkeypatch
) -> None:
    # No app may claim the server's admin/dashboard vhost.
    monkeypatch.setattr(
        "hop3.commands._helpers.config",
        SimpleNamespace(ADMIN_DOMAIN="admin.example.com"),
    )
    session = get_session_factory()()
    with pytest.raises(CatalogInstallError, match="already in use"):
        stage_catalog_app("nextcloud", "wiki", "", session, domain="admin.example.com")


def test_stage_rejects_underscore_domain(rooted, admin_domain) -> None:
    # '_' is the loopback catch-all, not a servable domain the user can request.
    session = get_session_factory()()
    with pytest.raises(CatalogInstallError, match="catch-all"):
        stage_catalog_app("nextcloud", "wiki", "", session, domain="_")


def test_stage_empty_domains_list_is_not_a_pin(rooted, admin_domain) -> None:
    # `list = []` is a deploy-time no-op, so it must NOT suppress auto-assign
    # (else the app would silently deploy loopback-only).
    recipe = rooted / "catalog" / "nextcloud" / "hop3.toml"
    recipe.write_text('[metadata]\nid = "nextcloud"\n[domains]\nlist = []\n')
    session = get_session_factory()()
    app = stage_catalog_app("nextcloud", "wiki", "", session)
    assert _host_name(app) == "wiki.apps.example.com"


def test_stage_env_host_name_recipe_pin_suppresses_auto(rooted, admin_domain) -> None:
    # A recipe pinning [env].HOST_NAME is a pin (covered separately from [domains]).
    recipe = rooted / "catalog" / "nextcloud" / "hop3.toml"
    recipe.write_text(
        '[metadata]\nid = "nextcloud"\n[env]\nHOST_NAME = "pinned.example.com"\n'
    )
    session = get_session_factory()()
    app = stage_catalog_app("nextcloud", "wiki", "", session)
    assert _host_name(app) is None
