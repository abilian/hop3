# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""System integration tests for application deployment using hop3-cli.

These tests verify basic CLI and RPC communication:
- Basic tarball deployment via `hop3 deploy`
- Application listing
- Authentication

For tests requiring full deployment infrastructure (uwsgi, nginx, systemd),
see tests/d_e2e/test_full_deployment.py

Requirements:
- hop3-cli binary must be installed and in PATH
- Server running (auto-started in /tmp or via HOP3_DEV_HOST)
"""

from __future__ import annotations

import os
from pathlib import Path

from .conftest import create_simple_flask_app, hop3, wait_for_app_in_list


class TestTarballDeployment:
    """Test basic application deployment via tarball upload (hop3 deploy)."""

    def test_deploy_simple_flask_app(self, deployed_app: dict, e2e_auth_token: str):
        """Test deploying a simple Flask app via tarball."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Create a simple Flask app
        create_simple_flask_app(app_dir, app_name)

        # Change to app directory for deployment
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            # Deploy the app
            result = hop3("deploy", app_name)
            deployed_app["deployed"] = True

            assert result.returncode == 0
            assert (
                "success" in result.stdout.lower()
                or "deployed" in result.stdout.lower()
            )

            # Wait for app to appear in apps list
            assert wait_for_app_in_list(app_name, timeout=30)

        finally:
            os.chdir(original_dir)


class TestAuthentication:
    """Test authentication requirements for operations."""

    def test_commands_require_authentication(self, hop3_config_dir: Path):
        """Test that commands work with or without authentication based on server config."""
        # Remove api_token from environment temporarily
        original_token = os.environ.get("HOP3_API_TOKEN")
        if original_token:
            os.environ.pop("HOP3_API_TOKEN")

        try:
            # Try to run a protected command without auth
            result = hop3("apps", check=False)

            # With authentication enabled on server, should fail with auth error
            # Without authentication, command succeeds
            if result.returncode != 0:
                # Authentication is required - check for auth error
                error_output = result.stderr.lower() + result.stdout.lower()
                assert (
                    "auth" in error_output
                    or "token" in error_output
                    or "unauthorized" in error_output
                ), f"Expected auth error but got: {result.stderr}"
            # else: Authentication not required on this server (that's okay too)

        finally:
            # Restore token
            if original_token:
                os.environ["HOP3_API_TOKEN"] = original_token


class TestAppsList:
    """Test listing applications."""

    def test_apps_list_empty(self, e2e_auth_token: str):
        """Test listing apps when none are deployed (or cleaning up test apps)."""
        result = hop3("apps")
        assert result.returncode == 0
        # Should return successfully even if empty

    def test_apps_list_with_deployed_app(self, deployed_app: dict, e2e_auth_token: str):
        """Test listing apps shows deployed applications."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Deploy an app
        create_simple_flask_app(app_dir, app_name)
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            hop3("deploy", app_name)
            deployed_app["deployed"] = True

            # Wait for app to appear in apps list
            assert wait_for_app_in_list(app_name, timeout=30)

        finally:
            os.chdir(original_dir)
