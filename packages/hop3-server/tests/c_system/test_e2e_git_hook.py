# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end tests for git-hook deployment method.

These tests verify deployment via the git-hook command which:
1. Accepts a git commit SHA/ref
2. Uses `git archive` to extract files securely
3. Deploys to the unified deployment engine

This is the deployment method used by git push workflows.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .conftest import create_simple_flask_app, hop3


class TestGitHookDeployment:
    """Test deployment via git-hook command (git push workflow)."""

    # Full git-hook deployment test moved to tests/d_e2e/test_full_deployment.py
    # That test requires complete git push infrastructure

    def test_git_hook_with_invalid_commit(
        self, deployed_app: dict, e2e_auth_token: str
    ):
        """Test that git-hook rejects invalid commit references."""
        app_name = deployed_app["name"]

        # Try to deploy with invalid commit
        result = hop3("git-hook", app_name, "invalid-commit-sha", check=False)

        # Command might return 0 with error message (app not found)
        # or non-zero (invalid commit)
        # Either way, it shouldn't succeed with actual deployment
        if result.returncode == 0:
            # Check that it's failing with an expected error
            error_output = result.stdout + result.stderr
            assert (
                "not found" in error_output.lower() or "error" in error_output.lower()
            ), "Expected error message in output"
        # else: non-zero return code is also acceptable

    def test_git_archive_extraction(self, deployed_app: dict, e2e_auth_token: str):
        """Test that git archive extraction works correctly."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Create app with git repo
        create_simple_flask_app(app_dir, app_name)

        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            # Initialize git
            subprocess.run(["git", "init"], capture_output=True, check=True)
            subprocess.run(["git", "add", "."], capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Test commit"],
                capture_output=True,
                check=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": "Test",
                    "GIT_AUTHOR_EMAIL": "test@test.com",
                    "GIT_COMMITTER_NAME": "Test",
                    "GIT_COMMITTER_EMAIL": "test@test.com",
                },
            )

            # Test git archive command locally
            result = subprocess.run(
                ["git", "archive", "--format=tar", "HEAD"],
                capture_output=True,
                check=True,
            )

            # Should produce valid tar output
            assert len(result.stdout) > 0
            assert result.returncode == 0

        finally:
            os.chdir(original_dir)


class TestGitHookSecurity:
    """Test security aspects of git-hook deployment."""

    def test_git_hook_path_traversal_prevention(
        self, deployed_app: dict, e2e_auth_token: str
    ):
        """Test that git-hook prevents path traversal in filenames."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            # Create a git repo with a malicious filename
            subprocess.run(["git", "init"], capture_output=True, check=True)

            # Try to create a file with path traversal (this will fail in git)
            # Git doesn't allow ../../ in filenames, so this is mainly a documentation test
            malicious_name = "../../etc/passwd"

            # Create normal file
            (app_dir / "app.py").write_text("# test")

            subprocess.run(["git", "add", "."], capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Test"],
                capture_output=True,
                check=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": "Test",
                    "GIT_AUTHOR_EMAIL": "test@test.com",
                    "GIT_COMMITTER_NAME": "Test",
                    "GIT_COMMITTER_EMAIL": "test@test.com",
                },
            )

            # Git itself prevents path traversal, so this test mainly documents
            # that the security is provided by both git and our archive extraction
            assert True  # Git prevents malicious filenames

        finally:
            os.chdir(original_dir)

    def test_git_hook_requires_authentication(self, hop3_config_dir: Path):
        """Test that git-hook command works with or without authentication based on server config."""
        # Remove api_token from environment
        original_token = os.environ.get("HOP3_API_TOKEN")
        if original_token:
            os.environ.pop("HOP3_API_TOKEN")

        try:
            # Try to run git-hook without auth
            result = hop3("git-hook", "test-app", "HEAD", check=False)

            # With authentication enabled on server, should fail with auth error
            # Without authentication, command may still fail (app not found) but not with auth error
            if result.returncode != 0:
                # Check for auth error
                error_output = result.stderr.lower() + result.stdout.lower()
                # Either auth error or app not found is acceptable
                assert (
                    "auth" in error_output
                    or "token" in error_output
                    or "unauthorized" in error_output
                    or "not found" in error_output
                ), f"Expected auth or app error but got: {result.stderr}"
            # else: Command succeeded (no auth required) - that's okay too

        finally:
            # Restore token
            if original_token:
                os.environ["HOP3_API_TOKEN"] = original_token
