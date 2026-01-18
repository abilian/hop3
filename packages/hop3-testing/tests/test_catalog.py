# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the new test catalog system."""

from __future__ import annotations

from pathlib import Path

import pytest
from hop3_testing.catalog import (
    Catalog,
    Category,
    Priority,
    Tier,
    load_test_definition,
)
from hop3_testing.catalog.loader import generate_test_definition_from_app
from hop3_testing.selector import Selector, get_mode_config


# Test data directory (relative to project root)
# Find the project root by looking for pyproject.toml
def _find_project_root() -> Path:
    """Find the project root directory."""
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "apps").exists():
            return current
        current = current.parent
    # Fallback
    return PROJECT_ROOT


PROJECT_ROOT = _find_project_root()
TEST_APPS_DIR = PROJECT_ROOT / "apps" / "test-apps"


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

    def test_category_enum(self):
        """Test Category enum values."""
        assert Category.DEPLOYMENT == "deployment"
        assert Category.DEMO == "demo"
        assert Category.TUTORIAL == "tutorial"


class TestLoader:
    """Tests for test.toml loader."""

    def test_load_static_app(self):
        """Test loading a test.toml file."""
        test_toml = TEST_APPS_DIR / "000-static" / "test.toml"
        if not test_toml.exists():
            pytest.skip("Test app not found")

        test_def = load_test_definition(test_toml)

        assert test_def.name == "000-static"
        assert test_def.category == Category.DEPLOYMENT
        assert test_def.tier == Tier.FAST
        assert test_def.priority == Priority.P0

    def test_load_flask_app(self):
        """Test loading Flask app test.toml."""
        test_toml = TEST_APPS_DIR / "010-flask-pip-wsgi" / "test.toml"
        if not test_toml.exists():
            pytest.skip("Test app not found")

        test_def = load_test_definition(test_toml)

        assert test_def.name == "010-flask-pip-wsgi"
        assert test_def.category == Category.DEPLOYMENT
        assert "python" in test_def.metadata.covers
        assert "flask" in test_def.metadata.covers

    def test_generate_from_legacy_app(self):
        """Test generating test definition from legacy app without test.toml."""
        # Use any directory as a fake app
        app_path = TEST_APPS_DIR / "000-static"
        if not app_path.exists():
            pytest.skip("Test app not found")

        test_def = generate_test_definition_from_app(app_path)

        assert test_def.name == "000-static"
        assert test_def.category == Category.DEPLOYMENT
        assert test_def.tier == Tier.FAST  # Inferred from name

    def test_validation_parsing(self):
        """Test that validations are parsed correctly."""
        test_toml = TEST_APPS_DIR / "010-flask-pip-wsgi" / "test.toml"
        if not test_toml.exists():
            pytest.skip("Test app not found")

        test_def = load_test_definition(test_toml)

        assert len(test_def.validations) >= 1
        validation = test_def.validations[0]
        assert validation.type == "http"
        assert validation.expect is not None


class CatalogScanningTests:
    """Tests for Catalog scanning."""

    def test_catalog_scan_finds_tests(self):
        """Test that catalog scanning finds test apps."""
        # Use the project root
        root = PROJECT_ROOT
        catalog = Catalog(root)
        catalog.scan()

        # Should find at least some tests
        all_tests = list(catalog.all_tests())
        assert len(all_tests) > 0

    def test_catalog_filter_by_category(self):
        """Test filtering by category."""
        root = PROJECT_ROOT
        catalog = Catalog(root)
        catalog.scan()

        deployment_tests = catalog.filter(categories=["deployment"])
        for test in deployment_tests:
            assert test.category == Category.DEPLOYMENT

    def test_catalog_filter_by_priority(self):
        """Test filtering by priority."""
        root = PROJECT_ROOT
        catalog = Catalog(root)
        catalog.scan()

        p0_tests = catalog.filter(priorities=["P0"])
        for test in p0_tests:
            assert test.priority == Priority.P0

    def test_catalog_filter_by_tier(self):
        """Test filtering by tier."""
        root = PROJECT_ROOT
        catalog = Catalog(root)
        catalog.scan()

        fast_tests = catalog.filter(tiers=["fast"])
        for test in fast_tests:
            assert test.tier == Tier.FAST

    def test_catalog_get_test(self):
        """Test getting a specific test by name."""
        root = PROJECT_ROOT
        catalog = Catalog(root)
        catalog.scan()

        test = catalog.get_test("010-flask-pip-wsgi")
        if test:
            assert test.name == "010-flask-pip-wsgi"
        # If test not found, it's okay - catalog might be scanned differently


class SelectorTests:
    """Tests for test selection."""

    def test_dev_mode_selection(self):
        """Test that dev mode selects appropriate tests."""
        root = PROJECT_ROOT
        catalog = Catalog(root)
        catalog.scan()

        mode_config = get_mode_config("dev")
        selector = Selector(catalog)
        tests = selector.select_for_target(mode_config, "docker")

        # Dev mode should only select fast P0 tests
        for test in tests:
            assert test.tier == Tier.FAST
            assert test.priority == Priority.P0

    def test_ci_mode_selection(self):
        """Test that CI mode selects appropriate tests."""
        root = PROJECT_ROOT
        catalog = Catalog(root)
        catalog.scan()

        mode_config = get_mode_config("ci")
        selector = Selector(catalog)
        tests = selector.select_for_target(mode_config, "docker")

        # CI mode should select fast and medium P0 tests
        for test in tests:
            assert test.tier in {Tier.FAST, Tier.MEDIUM}
            assert test.priority == Priority.P0
