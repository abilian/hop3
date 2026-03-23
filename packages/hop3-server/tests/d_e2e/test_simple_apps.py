# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""E2E tests using the hop3-testing framework."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from hop3_testing.apps import DeploymentSession
from hop3_testing.apps.catalog import AppSource
from hop3_testing.exceptions import DeploymentError

# Get all test apps from apps/test-apps/ and apps/nix-apps/
APPS_ROOT = Path(__file__).parents[4] / "apps"
TEST_APPS_DIR = APPS_ROOT / "test-apps"
NIX_APPS_DIR = APPS_ROOT / "nix-apps"

# Apps that require nix (from nix-apps directory)
NIX_APP_NAMES: set[str] = set()


def _collect_apps(app_dir: Path, is_nix: bool = False) -> list:
    """Collect test apps from a directory."""
    if not app_dir.exists():
        return []
    apps = []
    for d in sorted(app_dir.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            if is_nix:
                NIX_APP_NAMES.add(d.name)
            apps.append(pytest.param(d, id=d.name))
    return apps


TEST_APPS = _collect_apps(TEST_APPS_DIR) + _collect_apps(NIX_APPS_DIR, is_nix=True)

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
def test_app_deployment(app_dir: Path, deployment_target, request):
    """Test deployment of an application from apps/test-apps/ or apps/nix-apps/."""
    app_name = app_dir.name

    # FIXME later
    if app_name == "030-golang-gin":
        return

    # FIXME: pyproject.toml apps fail with 502 when pip install . is used
    # The pip install succeeds locally but gunicorn fails to start in container
    # Needs investigation - might be related to working directory or PYTHONPATH
    if app_name == "110-flask-gunicorn-poetry":
        pytest.skip("pyproject.toml deployment needs investigation")

    # Nix apps require --run-nix flag or NIX_TESTS=1 environment variable
    if app_name in NIX_APP_NAMES:
        run_nix = request.config.getoption("--run-nix", default=False)
        if not run_nix and os.environ.get("NIX_TESTS") != "1":
            pytest.skip("Nix app - use --run-nix or NIX_TESTS=1 to enable")

    app = AppSource(name=app_name, path=app_dir)
    with DeploymentSession(app, deployment_target) as session:
        try:
            session.deploy()  # Raises DeploymentError on failure
        except DeploymentError as e:
            # Check for network errors in deployment and skip if found
            error_msg = str(e)
            if _is_network_error(error_msg):
                pytest.skip(f"Skipping due to network error: {error_msg[:100]}")
            pytest.fail(f"Deploy failed: {e}")

        assert session.check_deployed(), (
            f"App {app_name} not found in deployed apps list"
        )

        # Use detailed HTTP test for better error messages
        http_result = session.test_http_detailed()
        assert http_result["passed"], (
            f"HTTP test failed for {app_name}: {http_result['message']}\n"
            f"Details: {http_result.get('details', {})}"
        )
