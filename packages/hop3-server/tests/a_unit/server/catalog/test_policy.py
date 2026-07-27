# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the catalog spec-validation gate (ADR 049 F7)."""

from __future__ import annotations

import logging

import pytest

from hop3.server.catalog import loader
from hop3.server.catalog.loader import load_apps
from hop3.server.catalog.policy import (
    CatalogSpecError,
    validate_catalog_app_files,
    validate_catalog_spec,
)


def test_spec_without_domains_is_allowed():
    validate_catalog_spec({"metadata": {"id": "x"}}, "x")  # no raise


def test_specific_hostname_is_allowed():
    # A concrete host does not hijack neighbours (nginx routes by Host header).
    validate_catalog_spec({"domains": {"list": ["app.example.com"]}}, "x")


def test_catch_all_host_rejected():
    with pytest.raises(CatalogSpecError, match="catch-all"):
        validate_catalog_spec({"domains": {"list": ["_"]}}, "owncast")


def test_wildcard_host_rejected():
    with pytest.raises(CatalogSpecError, match="wildcard"):
        validate_catalog_spec({"domains": {"list": ["*.example.com"]}}, "x")


def test_catch_all_in_context_rejected():
    # ADR 042 r2: plural `contexts` key, domains in the [domains].list shape.
    spec = {"contexts": {"prod": {"domains": {"list": ["_"]}}}}
    with pytest.raises(CatalogSpecError, match="catch-all"):
        validate_catalog_spec(spec, "x")


def test_hosts_alias_key_also_checked():
    # The schema field name `hosts` is accepted alongside the TOML alias `list`.
    with pytest.raises(CatalogSpecError, match="catch-all"):
        validate_catalog_spec({"domains": {"hosts": ["_"]}}, "x")


def _write_app(catalog_dir, app_id, *, toml: str):
    d = catalog_dir / app_id
    d.mkdir(parents=True)
    (d / "hop3.toml").write_text(toml)


def test_loader_excludes_violating_app_loudly(tmp_path):
    cat = tmp_path / "catalog"
    _write_app(cat, "good", toml='[metadata]\nid = "good"\ntitle = "Good"\n')
    _write_app(
        cat,
        "hijacker",
        toml='[metadata]\nid = "hijacker"\n[domains]\nlist = ["_"]\n',
    )

    # Capture log records explicitly — more robust than caplog across environments.
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append
    handler.setLevel(logging.ERROR)
    loader.logger.addHandler(handler)
    try:
        apps = load_apps(cat)
    finally:
        loader.logger.removeHandler(handler)

    assert {a.id for a in apps} == {"good"}  # violator excluded
    assert any("hijacker" in r.getMessage() for r in records)  # surfaced, not silent


# Buildability gate — a blueprint that cannot build must not ship


def test_unpinned_requirements_are_rejected_at_publish(tmp_path):
    """
    Regression: the catalog shipped bugsink with `gunicorn>=21.0`.

    The Python toolchain refuses unpinned requirements as unreproducible, so the
    build aborted on the node — leaving an empty venv, `gunicorn: not found`,
    and a generic start timeout. Catch it in the release, not in every install.
    """
    app_dir = tmp_path / "bugsink"
    app_dir.mkdir()
    (app_dir / "requirements.txt").write_text(
        "bugsink==2.1.2\ngunicorn>=21.0\npsycopg2-binary>=2.9\n"
    )

    with pytest.raises(CatalogSpecError, match=r"unpinned requirements\.txt"):
        validate_catalog_app_files(app_dir, "bugsink")


def test_pinned_requirements_pass(tmp_path):
    app_dir = tmp_path / "bugsink"
    app_dir.mkdir()
    (app_dir / "requirements.txt").write_text(
        "bugsink==2.1.2\ngunicorn==25.1.0\npsycopg2-binary==2.9.12\n"
    )

    validate_catalog_app_files(app_dir, "bugsink")  # must not raise


def test_app_without_requirements_is_not_gated(tmp_path):
    """Non-Python blueprints (PHP, static, nix) have no requirements.txt."""
    app_dir = tmp_path / "wordpress"
    app_dir.mkdir()
    (app_dir / "hop3.toml").write_text("[metadata]\nid = 'wordpress'\n")

    validate_catalog_app_files(app_dir, "wordpress")  # must not raise
