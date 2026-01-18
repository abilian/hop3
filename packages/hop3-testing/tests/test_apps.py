# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the testing framework itself."""

from __future__ import annotations

from pathlib import Path

import pytest
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
    catalog.scan()
    return catalog


def test_catalog_discovers_tests():
    """Test that catalog can find tests."""
    catalog = get_catalog()

    # Should find some tests
    assert len(catalog) > 0, "No tests found"

    # Check categories
    categories = catalog.categories()
    assert len(categories) > 0, "No categories found"

    # Check we can retrieve specific tests
    flask_test = catalog.get_test("010-flask-pip-wsgi")
    if flask_test:
        assert flask_test.category.value == "deployment"
        # Check metadata covers tags
        assert "python" in flask_test.metadata.covers


def test_catalog_filtering():
    """Test filtering tests."""
    catalog = get_catalog()

    # Filter by category
    deployment_tests = catalog.filter(categories=["deployment"])
    for test in deployment_tests:
        assert test.category.value == "deployment"

    # Filter by tags
    python_tests = catalog.filter(tags=["python"])
    for test in python_tests:
        assert "python" in test.metadata.covers


def test_catalog_properties():
    """Test TestDefinition properties."""
    catalog = get_catalog()

    static_test = catalog.get_test("000-static")
    if not static_test:
        pytest.skip("Static test not found")

    # Check app_path exists
    assert static_test.app_path is not None
    assert static_test.app_path.exists()
    assert static_test.app_path.is_dir()

    # Check name
    assert static_test.name == "000-static"

    # Check has validations
    assert len(static_test.validations) > 0
