# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the catalog spec-validation gate (ADR 049 F7)."""

from __future__ import annotations

import logging

import pytest

from hop3.server.catalog.loader import load_apps
from hop3.server.catalog.policy import CatalogSpecError, validate_catalog_spec


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
    spec = {"context": {"prod": {"domains": ["_"]}}}
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


def test_loader_excludes_violating_app_loudly(tmp_path, caplog):
    cat = tmp_path / "catalog"
    _write_app(cat, "good", toml='[metadata]\nid = "good"\ntitle = "Good"\n')
    _write_app(
        cat,
        "hijacker",
        toml='[metadata]\nid = "hijacker"\n[domains]\nlist = ["_"]\n',
    )

    with caplog.at_level(logging.ERROR):
        apps = load_apps(cat)

    assert {a.id for a in apps} == {"good"}  # violator excluded
    assert any("hijacker" in r.message for r in caplog.records)  # surfaced, not silent
