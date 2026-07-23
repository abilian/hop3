# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the test catalog system."""

from __future__ import annotations

from pathlib import Path

import pytest
from hop3_testing.catalog import (
    Catalog,
    Priority,
    Tier,
    load_test_definition,
)
from hop3_testing.catalog.loader import generate_test_definition_from_app
from hop3_testing.selector import Selector, get_mode_config


# Test data directory (relative to project root)
def _find_project_root() -> Path:
    """Find the project root directory."""
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "apps").exists():
            return current
        current = current.parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root()
TEST_APPS_DIR = PROJECT_ROOT / "apps" / "test-apps-procfile"


class TestModels:
    """Tests for catalog models."""

    def test_tier_enum(self):
        """Test Tier enum values."""
        assert Tier.FAST == "fast"
        assert Tier.MEDIUM == "medium"
        assert Tier.SLOW == "slow"
        assert Tier.VERY_SLOW == "very-slow"

    def test_priority_enum(self):
        """Test Priority enum values."""
        assert Priority.P0 == "P0"
        assert Priority.P1 == "P1"
        assert Priority.P2 == "P2"


class TestLoader:
    """Tests for test.toml loader."""

    def test_load_static_app(self):
        """Test loading a test.toml file."""
        test_toml = TEST_APPS_DIR / "000-static" / "test.toml"
        test_def = load_test_definition(test_toml)

        assert test_def.name == "000-static"
        assert test_def.tier == Tier.FAST
        assert test_def.priority == Priority.P0

    def test_load_flask_app(self):
        """Test loading Flask app test.toml."""
        test_toml = TEST_APPS_DIR / "010-flask-pip-wsgi" / "test.toml"
        test_def = load_test_definition(test_toml)

        assert test_def.name == "010-flask-pip-wsgi"
        assert "python" in test_def.metadata.covers
        assert "flask" in test_def.metadata.covers

    def test_generate_from_app(self):
        """Test generating test definition from app directory."""
        app_path = TEST_APPS_DIR / "000-static"
        test_def = generate_test_definition_from_app(app_path)

        assert test_def.name == "000-static"
        assert test_def.runner_type == "deployment"
        assert test_def.tier == Tier.FAST

    def test_validation_parsing(self):
        """Test that validations are parsed correctly."""
        test_toml = TEST_APPS_DIR / "010-flask-pip-wsgi" / "test.toml"
        test_def = load_test_definition(test_toml)

        assert len(test_def.validations) >= 1
        validation = test_def.validations[0]
        assert validation.type == "http"
        assert validation.expect is not None


class CatalogScanningTests:
    """Tests for Catalog scanning."""

    def test_catalog_scan_finds_tests(self):
        """Test that catalog scanning finds test apps."""
        catalog = Catalog(PROJECT_ROOT)
        catalog.scan(paths=["apps/test-apps"])

        all_tests = list(catalog.all_tests())
        assert len(all_tests) > 0

    def test_catalog_filter_by_priority(self):
        """Test filtering by priority."""
        catalog = Catalog(PROJECT_ROOT)
        catalog.scan(paths=["apps/test-apps"])

        p0_tests = catalog.filter(priorities=["P0"])
        for test in p0_tests:
            assert test.priority == Priority.P0

    def test_catalog_filter_by_tier(self):
        """Test filtering by tier."""
        catalog = Catalog(PROJECT_ROOT)
        catalog.scan(paths=["apps/test-apps"])

        fast_tests = catalog.filter(tiers=["fast"])
        for test in fast_tests:
            assert test.tier == Tier.FAST

    def test_catalog_get_test(self):
        """Test getting a specific test by name."""
        catalog = Catalog(PROJECT_ROOT)
        catalog.scan(paths=["apps/test-apps"])

        test = catalog.get_test("apps/test-apps/010-flask-pip-wsgi")
        if test:
            assert test.name == "apps/test-apps/010-flask-pip-wsgi"

    def test_catalog_scan_demos(self):
        """Test that demos are discovered."""
        catalog = Catalog(PROJECT_ROOT)
        catalog.scan(paths=["demos"])

        all_tests = list(catalog.all_tests())
        assert len(all_tests) > 0

        # Demos should have runner_type "demo"
        demo_tests = [t for t in all_tests if t.runner_type == "demo"]
        assert len(demo_tests) > 0

    def test_catalog_scan_requires_paths(self):
        """Test that scan raises ValueError without paths."""
        catalog = Catalog(PROJECT_ROOT)
        with pytest.raises(ValueError):
            catalog.scan()


class SelectorTests:
    """Tests for test selection."""

    def test_dev_mode_selection(self):
        """Test that dev mode selects appropriate tests."""
        catalog = Catalog(PROJECT_ROOT)
        catalog.scan(paths=["apps/test-apps"])

        mode_config = get_mode_config("dev")
        selector = Selector(catalog)
        tests = selector.select_for_target(mode_config, "docker")

        # Dev mode should only select fast P0 tests
        for test in tests:
            assert test.tier == Tier.FAST
            assert test.priority == Priority.P0

    def test_ci_mode_selection(self):
        """Test that CI mode selects appropriate tests."""
        catalog = Catalog(PROJECT_ROOT)
        catalog.scan(paths=["apps/test-apps"])

        mode_config = get_mode_config("ci")
        selector = Selector(catalog)
        tests = selector.select_for_target(mode_config, "docker")

        # CI mode should select fast and medium P0 tests
        for test in tests:
            assert test.tier in {Tier.FAST, Tier.MEDIUM}
            assert test.priority == Priority.P0


def test_demo_internal_app_not_discovered_when_scanning_demo_dir():
    """
    A demo's private deploy target (demos/demoNN/app/) must not be discovered
    as a standalone test — however the scan entered.

    Regression: `hop3-test run demos/demo60` scans the demo dir directly, so the
    old child-scan guard saw only `app/` (no demo-script.py inside it) and let
    `demos/demo60/app/hop3.toml` leak as its own app test — which then failed the
    bare-status / proxy-502 checks. The thing to run is the demo, not its app.
    """
    # a) Scan the demo dir directly — the failing entry point.
    catalog = Catalog(PROJECT_ROOT)
    catalog.scan(paths=["demos/demo60"])
    names = {t.name for t in catalog.all_tests()}
    assert not any(n.endswith("/app") for n in names), (
        f"demo-internal app leaked: {names}"
    )
    assert any(t.runner_type == "demo" for t in catalog.all_tests()), (
        "the demo itself must still be discovered"
    )

    # b) Scan the demos/ parent — no inner app may leak from any demo.
    catalog = Catalog(PROJECT_ROOT)
    catalog.scan(paths=["demos"])
    leaked = [t.name for t in catalog.all_tests() if t.name.endswith("/app")]
    assert not leaked, f"inner demo apps leaked from parent scan: {leaked}"
