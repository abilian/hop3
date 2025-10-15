# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the testing framework itself."""

from __future__ import annotations

import pytest
from hop3_testing.apps import TestAppCatalog


def test_test_app_catalog():
    """Test that TestAppCatalog can find test apps."""
    catalog = TestAppCatalog()

    # Should find some apps
    assert len(catalog) > 0, "No test apps found"

    # Check categories
    categories = catalog.list_categories()
    assert len(categories) > 0, "No categories found"

    # Check we can retrieve specific apps (if they exist)
    # Note: 000-static app may not exist in all test environments
    flask_app = catalog.get("010-flask-pip-wsgi")
    if flask_app:
        assert flask_app.category == "python-simple"


def test_test_app_filtering():
    """Test filtering test apps."""
    catalog = TestAppCatalog()

    # Filter by category
    python_apps = list(catalog.filter(category="python-simple"))
    for app in python_apps:
        assert app.category == "python-simple"


def test_test_app_properties():
    """Test TestApp properties."""
    catalog = TestAppCatalog()

    static_app = catalog.get("000-static")
    if not static_app:
        pytest.skip("Static app not found")

    # Check path exists
    assert static_app.path.exists()
    assert static_app.path.is_dir()

    # Check name
    assert static_app.name == "000-static"

    # Check has_procfile
    assert isinstance(static_app.has_procfile, bool)

    # Check has_check_script
    assert isinstance(static_app.has_check_script, bool)
