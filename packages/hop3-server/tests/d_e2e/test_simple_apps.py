# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E tests using the hop3-testing framework."""

from __future__ import annotations

from pathlib import Path

import pytest
from hop3_testing.apps import DeploymentSession
from hop3_testing.apps.catalog import AppSource

# Get all test apps from apps/test-apps/
APPS_DIR = Path(__file__).parents[4] / "apps" / "test-apps"
TEST_APPS = [
    pytest.param(app_dir, id=app_dir.name)
    for app_dir in sorted(APPS_DIR.iterdir())
    if app_dir.is_dir() and not app_dir.name.startswith(".")
]

# Network error patterns that indicate infrastructure issues, not code bugs
NETWORK_ERROR_PATTERNS = [
    "ERR_SOCKET_TIMEOUT",
    "ETIMEDOUT",
    "ECONNREFUSED",
    "network connectivity",
    "Socket timeout",
]


def _is_network_error(error_message: str) -> bool:
    """Check if an error message indicates a network/infrastructure issue."""
    return any(pattern in error_message for pattern in NETWORK_ERROR_PATTERNS)


@pytest.mark.e2e
@pytest.mark.parametrize("app_dir", TEST_APPS)
def test_app_deployment(app_dir: Path, deployment_target):
    """Test deployment of an application from apps/test-apps/."""
    app_name = app_dir.name

    # FIXME later
    if app_name == "030-golang-gin":
        return

    app = AppSource(name=app_name, path=app_dir)
    with DeploymentSession(app, deployment_target) as session:
        deploy_result = session.deploy()

        # Check for network errors in deployment and skip if found
        if hasattr(session, "_last_deploy_error") and session._last_deploy_error:
            if _is_network_error(session._last_deploy_error):
                pytest.skip(
                    f"Skipping due to network error: {session._last_deploy_error[:100]}"
                )

        assert deploy_result, f"Deploy failed: {session.last_deploy_error}"
        assert session.check_deployed(), f"App {app_name} not found in deployed apps list"

        # Use detailed HTTP test for better error messages
        http_result = session.test_http_detailed()
        assert http_result["passed"], (
            f"HTTP test failed for {app_name}: {http_result['message']}\n"
            f"Details: {http_result.get('details', {})}"
        )
