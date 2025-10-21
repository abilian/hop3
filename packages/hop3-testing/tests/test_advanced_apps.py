# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for advanced applications (different frameworks, languages, etc.)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hop3_testing.apps import DeploymentSession

APPS = [
    "020-nodejs-express",
    "030-golang-gin",
    "040-sinatra100-flask-gunicorn-pip",
    "110-flask-gunicorn-poetry",
]

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget


@pytest.mark.deployment
@pytest.mark.slow
@pytest.mark.parametrize("app_name", APPS)
def test_deploy_simple_app(
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

    # with DeploymentSession(test_app, deployment_target) as session:
    #     session.prepare()
    #     assert session.deploy(wait_time=30), "Deployment failed"
    #     assert session.check_deployed(), "App not deployed"
    #     assert session.test_http(max_retries=50), "HTTP test failed"


# @pytest.mark.deployment
# @pytest.mark.slow
# def test_nodejs_app(
#     deployment_target: DeploymentTarget,
#     test_app_catalog,
# ):
#     """Test deploying a Node.js Express application.
#
#     Args:
#         deployment_target: Deployment target fixture
#         test_app_catalog: Test app catalog fixture
#     """
#     app = test_app_catalog.get("020-nodejs-express")
#     if not app:
#         pytest.skip("Node.js app not found")
#
#     with DeploymentSession(app, deployment_target) as session:
#         session.prepare()
#         assert session.deploy(wait_time=30), "Deployment failed"
#         assert session.check_deployed(), "App not deployed"
#         assert session.test_http(max_retries=50), "HTTP test failed"
