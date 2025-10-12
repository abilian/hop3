# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for advanced applications (different frameworks, languages, etc.)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hop3_testing.apps import DeploymentSession

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget


@pytest.mark.deployment
@pytest.mark.slow
@pytest.mark.parametrize(
    "app_name",
    [
        "020-nodejs-express",
        "100-flask-gunicorn-pip",
        "110-flask-gunicorn-poetry",
    ],
)
def test_deploy_advanced_app(
    deployment_target: DeploymentTarget,
    test_app_catalog,
    app_name: str,
):
    """Test deploying advanced applications.

    Args:
        deployment_target: Deployment target fixture
        test_app_catalog: Test app catalog fixture
        app_name: Application name to test
    """
    test_app = test_app_catalog.get(app_name)
    if not test_app:
        pytest.skip(f"App {app_name} not found")

    session = DeploymentSession(test_app, deployment_target)
    assert session.run_full_test(), f"Deployment test failed for {app_name}"


@pytest.mark.deployment
@pytest.mark.slow
def test_nodejs_app(
    deployment_target: DeploymentTarget,
    test_app_catalog,
):
    """Test deploying a Node.js Express application.

    Args:
        deployment_target: Deployment target fixture
        test_app_catalog: Test app catalog fixture
    """
    app = test_app_catalog.get("020-nodejs-express")
    if not app:
        pytest.skip("Node.js app not found")

    with DeploymentSession(app, deployment_target) as session:
        session.prepare()
        assert session.deploy(wait_time=30), "Deployment failed"
        assert session.check_deployed(), "App not deployed"
        assert session.test_http(max_retries=50), "HTTP test failed"


@pytest.mark.deployment
@pytest.mark.slow
@pytest.mark.skip(reason="Poetry support not yet fully implemented")
def test_poetry_app(
    deployment_target: DeploymentTarget,
    test_app_catalog,
):
    """Test deploying a Python app with Poetry.

    Args:
        deployment_target: Deployment target fixture
        test_app_catalog: Test app catalog fixture
    """
    app = test_app_catalog.get("110-flask-gunicorn-poetry")
    if not app:
        pytest.skip("Poetry app not found")

    session = DeploymentSession(app, deployment_target)
    assert session.run_full_test(), "Poetry app deployment failed"


@pytest.mark.deployment
@pytest.mark.slow
@pytest.mark.skip(reason="Golang support not yet fully implemented")
def test_golang_app(
    deployment_target: DeploymentTarget,
    test_app_catalog,
):
    """Test deploying a Golang application.

    Args:
        deployment_target: Deployment target fixture
        test_app_catalog: Test app catalog fixture
    """
    app = test_app_catalog.get("030-golang-gin")
    if not app:
        pytest.skip("Golang app not found")

    session = DeploymentSession(app, deployment_target)
    assert session.run_full_test(), "Golang app deployment failed"


@pytest.mark.deployment
@pytest.mark.slow
@pytest.mark.skip(reason="Ruby support not yet fully implemented")
def test_ruby_app(
    deployment_target: DeploymentTarget,
    test_app_catalog,
):
    """Test deploying a Ruby Sinatra application.

    Args:
        deployment_target: Deployment target fixture
        test_app_catalog: Test app catalog fixture
    """
    app = test_app_catalog.get("040-sinatra")
    if not app:
        pytest.skip("Ruby app not found")

    session = DeploymentSession(app, deployment_target)
    assert session.run_full_test(), "Ruby app deployment failed"
