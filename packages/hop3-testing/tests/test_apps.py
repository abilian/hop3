# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the testing framework itself."""

from __future__ import annotations

from pathlib import Path

from hop3_testing.catalog import Catalog
from hop3_testing.targets.helpers import find_project_root


def get_catalog() -> Catalog:
    """Create a catalog with explicit project root."""
    try:
        root = find_project_root()
    except RuntimeError:
        # Fallback: navigate from test file
        root = Path(__file__).parent.parent.parent.parent.parent
    catalog = Catalog(root)
    catalog.scan(paths=["apps/test-apps-procfile", "apps/test-apps-nix"])
    return catalog


def test_catalog_discovers_tests():
    """Test that catalog can find tests."""
    catalog = get_catalog()

    # Should find some tests
    assert len(catalog) > 0, "No tests found"

    # Check we can retrieve specific tests
    flask_test = catalog.get_test("apps/test-apps-procfile/010-flask-pip-wsgi")
    assert flask_test is not None, "flask test app not found in catalog"
    assert flask_test.runner_type == "deployment"
    assert "python" in flask_test.metadata.covers


def test_catalog_filtering():
    """Test filtering tests."""
    catalog = get_catalog()

    # Filter by tags
    python_tests = catalog.filter(tags=["python"])
    for test in python_tests:
        assert "python" in test.metadata.covers


def test_catalog_properties():
    """Test TestDefinition properties."""
    catalog = get_catalog()

    static_test = catalog.get_test("apps/test-apps-procfile/000-static")
    assert static_test is not None, "static test app not found in catalog"

    # Check app_path exists
    assert static_test.app_path is not None
    assert static_test.app_path.exists()
    assert static_test.app_path.is_dir()

    # Check name
    assert static_test.name == "apps/test-apps-procfile/000-static"

    # Check has validations
    assert len(static_test.validations) > 0
