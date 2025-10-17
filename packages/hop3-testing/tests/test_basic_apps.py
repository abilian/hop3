# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Basic deployment tests for simple applications."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hop3_testing.apps import DeploymentSession

if TYPE_CHECKING:
    from hop3_testing.apps.catalog import TestApp
    from hop3_testing.targets.base import DeploymentTarget


@pytest.mark.deployment
@pytest.mark.parametrize("app", ["000-static", "010-flask-pip-wsgi"], indirect=False)
@pytest.mark.skip(
    reason="Migrated to d_e2e suite (packages/hop3-server/tests/d_e2e/). "
    "See local-notes/TEST-SUITE-CONSOLIDATION.md for details."
)
def test_deploy_basic_app(
    deployment_target: DeploymentTarget,
    test_app_catalog,
    app: str,
):
    """Test deploying basic applications.

    DEPRECATED: This test has been migrated to the d_e2e test suite.
    - Static app: test_static_deployment.py
    - Flask app: test_python_deployment.py and test_full_deployment.py

    Args:
        deployment_target: Deployment target fixture
        test_app_catalog: Test app catalog fixture
        app: Application name to test
    """
    test_app = test_app_catalog.get(app)
    if not test_app:
        pytest.skip(f"App {app} not found in catalog")

    # Create deployment session
    session = DeploymentSession(test_app, deployment_target)

    # Run full test cycle
    assert session.run_full_test(), f"Deployment test failed for {app}"


@pytest.mark.deployment
@pytest.mark.slow
@pytest.mark.skip(
    reason="Migrated to d_e2e suite (packages/hop3-server/tests/d_e2e/test_full_deployment.py). "
    "See local-notes/TEST-SUITE-CONSOLIDATION.md for details."
)
def test_deploy_all_simple_apps(
    deployment_target: DeploymentTarget,
    simple_apps: list[TestApp],
):
    """Test deploying all simple applications.

    DEPRECATED: This test has been migrated to the d_e2e test suite.
    The d_e2e suite provides more comprehensive lifecycle testing.

    This test deploys each simple app one by one and verifies it works.

    Args:
        deployment_target: Deployment target fixture
        simple_apps: List of simple test apps
    """
    if not simple_apps:
        pytest.skip("No simple apps found")

    results = []

    for test_app in simple_apps:
        print(f"\n{'=' * 60}")
        print(f"Testing: {test_app.name}")
        print(f"{'=' * 60}")

        session = DeploymentSession(test_app, deployment_target)
        success = session.run_full_test()
        results.append((test_app.name, success))

        if not success:
            print(f"❌ {test_app.name} failed")
        else:
            print(f"✓ {test_app.name} passed")

    # Print summary
    print(f"\n{'=' * 60}")
    print("Test Summary")
    print(f"{'=' * 60}")

    for app_name, success in results:
        status = "✓ PASS" if success else "❌ FAIL"
        print(f"{status}: {app_name}")

    # Check if all passed
    failed = [name for name, success in results if not success]
    if failed:
        pytest.fail(f"Failed apps: {', '.join(failed)}")


@pytest.mark.deployment
@pytest.mark.skip(
    reason="Migrated to d_e2e suite (packages/hop3-server/tests/d_e2e/test_static_deployment.py). "
    "See local-notes/TEST-SUITE-CONSOLIDATION.md for details."
)
def test_static_app_deployment(
    deployment_target: DeploymentTarget,
    test_app_catalog,
):
    """Test deploying a static HTML application.

    DEPRECATED: This test has been migrated to the d_e2e test suite.
    See test_static_deployment.py in d_e2e for the modern implementation.

    Args:
        deployment_target: Deployment target fixture
        test_app_catalog: Test app catalog fixture
    """
    app = test_app_catalog.get("000-static")
    if not app:
        pytest.skip("Static app not found")

    with DeploymentSession(app, deployment_target) as session:
        # Prepare and deploy
        session.prepare()
        assert session.deploy(), "Deployment failed"

        # Check deployment
        assert session.check_deployed(), "App not deployed"

        # Test HTTP access
        assert session.test_http(), "HTTP test failed"


@pytest.mark.deployment
@pytest.mark.skip(
    reason="Migrated to d_e2e suite (packages/hop3-server/tests/d_e2e/test_python_deployment.py "
    "and test_full_deployment.py). See local-notes/TEST-SUITE-CONSOLIDATION.md for details."
)
def test_flask_app_deployment(
    deployment_target: DeploymentTarget,
    test_app_catalog,
):
    """Test deploying a Flask application.

    DEPRECATED: This test has been migrated to the d_e2e test suite.
    The d_e2e suite provides more comprehensive Flask deployment testing with:
    - test_python_deployment.py: Basic Flask deployment
    - test_full_deployment.py: Complete lifecycle testing

    Args:
        deployment_target: Deployment target fixture
        test_app_catalog: Test app catalog fixture
    """
    app = test_app_catalog.get("010-flask-pip-wsgi")
    if not app:
        pytest.skip("Flask app not found")

    with DeploymentSession(app, deployment_target) as session:
        # Prepare and deploy
        session.prepare()
        assert session.deploy(wait_time=20), "Deployment failed"

        # Check deployment
        assert session.check_deployed(), "App not deployed"

        # Test HTTP access
        assert session.test_http(max_retries=40), "HTTP test failed"

        # Run check script if available
        if app.has_check_script:
            assert session.run_check_script(), "Check script failed"
