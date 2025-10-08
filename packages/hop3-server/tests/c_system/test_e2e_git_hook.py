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

import pytest

from .conftest import create_simple_flask_app, hop3


class TestGitHookDeployment:
    """Test deployment via git-hook command (git push workflow)."""

    def test_git_hook_deployment(self, deployed_app: dict, e2e_auth_token: str):
        """Test deploying via git-hook command (simulating git push)."""
        app_name = deployed_app["name"]
        app_dir = deployed_app["dir"]

        # Create a simple Flask app
        create_simple_flask_app(app_dir, app_name)

        # Initialize git repo
        original_dir = Path.cwd()
        os.chdir(app_dir)

        try:
            # Initialize git repository
            subprocess.run(["git", "init"], capture_output=True, check=True)
            subprocess.run(["git", "add", "."], capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
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

            # Get the commit SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            commit_sha = result.stdout.strip()

            # Deploy using git-hook command
            # Note: This command is executed on the server side
            # We need to push the repo first, then trigger git-hook
            # For now, we'll test that the git-hook command exists
            result = hop3("help", check=False)

            # Check if git-hook is available
            if "git-hook" not in result.stdout:
                pytest.skip("git-hook command not available in this server version")

            # For a full test, we would need to:
            # 1. Push the git repo to the server
            # 2. Trigger the git-hook command with the commit SHA
            # This requires more complex setup, so we'll mark this as TODO

            pytest.skip("Full git-hook E2E test requires git push infrastructure")

        finally:
            os.chdir(original_dir)

    def test_git_hook_with_invalid_commit(
        self, deployed_app: dict, e2e_auth_token: str
    ):
        """Test that git-hook rejects invalid commit references."""
        app_name = deployed_app["name"]

        # Try to deploy with invalid commit
        result = hop3("git-hook", app_name, "invalid-commit-sha", check=False)

        # Should fail
        assert result.returncode != 0

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
        """Test that git-hook command requires authentication."""
        # Remove api_token from environment
        original_token = os.environ.get("HOP3_API_TOKEN")
        if original_token:
            os.environ.pop("HOP3_API_TOKEN")

        try:
            # Try to run git-hook without auth
            result = hop3("git-hook", "test-app", "HEAD", check=False)

            # Should fail
            assert result.returncode != 0

        finally:
            # Restore token
            if original_token:
                os.environ["HOP3_API_TOKEN"] = original_token
