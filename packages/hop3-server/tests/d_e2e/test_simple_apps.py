# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E tests using the hop3-testing framework."""

from __future__ import annotations

from pathlib import Path

import pytest
from hop3_testing.apps import DeploymentSession
from hop3_testing.apps.catalog import TestApp

# Get all test apps from apps/test-apps/
APPS_DIR = Path(__file__).parents[4] / "apps" / "test-apps"
TEST_APPS = [
    pytest.param(app_dir, id=app_dir.name)
    for app_dir in sorted(APPS_DIR.iterdir())
    if app_dir.is_dir() and not app_dir.name.startswith(".")
]


@pytest.mark.e2e
@pytest.mark.parametrize("app_dir", TEST_APPS)
def test_app_deployment(app_dir: Path, deployment_target):
    """Test deployment of an application from apps/test-apps/."""
    app_name = app_dir.name
    app = TestApp(name=app_name, path=app_dir)
    with DeploymentSession(app, deployment_target) as session:
        assert session.deploy()
        assert session.check_deployed()
        assert session.test_http()
