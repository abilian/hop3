# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
End-to-end tests for git push deployment.

These tests verify the complete git push deployment workflow:
1. Create a local git repository with app code
2. Add a remote pointing to the Hop3 server
3. Push to the remote
4. Verify the app is deployed and running

Requirements:
- Docker must be running
- Tests use the hop3_container fixture from conftest.py
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from .conftest import FLASK_REQUIREMENTS, init_git_repo

if TYPE_CHECKING:
    from pathlib import Path


# Sample Flask app code for testing
FLASK_APP_CODE = """
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from git push!"

@app.route("/health")
def health():
    return {"status": "ok"}
"""


@pytest.fixture
def git_test_app(tmp_path: Path) -> Path:
    """
    Create a test Flask app with git repository.

    Returns:
        Path to the app directory with initialized git repo
    """
    app_dir = tmp_path / "git-push-test"
    app_dir.mkdir()

    # Create Flask app files
    (app_dir / "app.py").write_text(FLASK_APP_CODE)
    (app_dir / "requirements.txt").write_text(FLASK_REQUIREMENTS)
    (app_dir / "Procfile").write_text(
        "web: flask --app app run --host 0.0.0.0 --port $PORT\n"
    )

    # Initialize git repo
    init_git_repo(app_dir)

    return app_dir


def add_hop3_remote(
    app_dir: Path,
    container_info: dict[str, Any],
    app_name: str,
) -> None:
    """
    Add hop3 git remote to local repository.

    Args:
        app_dir: Path to local git repository
        container_info: Container fixture with SSH info
        app_name: Name of the app on the server
    """
    ssh_port = container_info["ssh_port"]
    ssh_key = container_info["ssh_key"]

    # Configure SSH to use our key and skip host key verification
    # This uses GIT_SSH_COMMAND environment variable
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = (
        f"ssh -i {ssh_key} -p {ssh_port} "
        f"-o StrictHostKeyChecking=no "
        f"-o UserKnownHostsFile=/dev/null"
    )

    # Remove existing remote if present
    subprocess.run(
        ["git", "remote", "remove", "hop3"],
        cwd=app_dir,
        capture_output=True,
        env=env,
        check=False,
    )

    # Add hop3 remote
    # The remote URL format is: hop3@localhost:app_name
    remote_url = f"hop3@localhost:{app_name}"
    subprocess.run(
        ["git", "remote", "add", "hop3", remote_url],
        cwd=app_dir,
        capture_output=True,
        env=env,
        check=True,
    )


def git_push_to_hop3(
    app_dir: Path,
    container_info: dict[str, Any],
    branch: str = "main",
) -> subprocess.CompletedProcess:
    """
    Push to hop3 remote.

    Args:
        app_dir: Path to local git repository
        container_info: Container fixture with SSH info
        branch: Branch name to push (default: main)

    Returns:
        CompletedProcess with push result
    """
    ssh_port = container_info["ssh_port"]
    ssh_key = container_info["ssh_key"]

    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = (
        f"ssh -i {ssh_key} -p {ssh_port} "
        f"-o StrictHostKeyChecking=no "
        f"-o UserKnownHostsFile=/dev/null"
    )

    # First, rename master to main if needed (git init creates master by default)
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=app_dir,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    if current_branch.stdout.strip() == "master" and branch == "main":
        subprocess.run(
            ["git", "branch", "-m", "master", "main"],
            cwd=app_dir,
            capture_output=True,
            env=env,
            check=True,
        )

    # Push to hop3 remote
    result = subprocess.run(
        ["git", "push", "-u", "hop3", branch],
        cwd=app_dir,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,  # Allow time for build
    )

    return result


@pytest.mark.e2e
class TestGitPushDeployment:
    """End-to-end tests for git push deployment."""

    def test_git_push_deploys_new_app(
        self,
        hop3_container: dict[str, Any],
        git_test_app: Path,
    ):
        """
        Test that git push creates and deploys a new app.

        ARRANGE:
            - Create local git repository with Flask app

        ACT:
            - Add hop3 remote
            - Push to hop3

        ASSERT:
            - Verify push succeeds
            - Verify deployment messages appear in output
            - Verify app was created and is running
        """
        app_name = "git-push-new-app"

        # Add remote and push
        add_hop3_remote(git_test_app, hop3_container, app_name)
        result = git_push_to_hop3(git_test_app, hop3_container)

        # Debug output
        print(f"Push stdout:\n{result.stdout}")
        print(f"Push stderr:\n{result.stderr}")

        # Check push succeeded (stderr contains git progress output)
        # The auto-create message appears in stderr (git remote messages go there)
        assert result.returncode == 0, f"Push failed: {result.stderr}"

        # Verify deployment happened by checking output
        combined_output = result.stdout + result.stderr
        assert "Deployment successful" in combined_output, (
            "Expected 'Deployment successful' in push output"
        )

        # Verify app was created and is running via container exec
        container = hop3_container["container"]

        # Check app directory exists
        result = container.exec_run(f"test -d /home/hop3/apps/{app_name}")
        assert result.exit_code == 0, f"App directory not created: {app_name}"

        # Check app source was extracted
        result = container.exec_run(f"test -f /home/hop3/apps/{app_name}/src/app.py")
        assert result.exit_code == 0, f"App source not extracted: {app_name}"

        # Verify source file content matches what we pushed
        result = container.exec_run(f"cat /home/hop3/apps/{app_name}/src/app.py")
        assert "Hello from git push" in result.output.decode(), (
            "Expected app code not found in deployed source"
        )

    def test_git_push_updates_existing_app(
        self,
        hop3_container: dict[str, Any],
        tmp_path: Path,
    ):
        """
        Test that git push updates an existing deployed app.

        ARRANGE:
            - Deploy initial version via git push
            - Modify app code

        ACT:
            - Push updated code

        ASSERT:
            - Verify push succeeds
            - Verify new code is deployed (source file updated)
        """
        app_name = "git-push-update-app"
        app_dir = tmp_path / "update-test"
        app_dir.mkdir()
        container = hop3_container["container"]

        # Create initial version
        initial_code = """
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Version 1"
"""
        (app_dir / "app.py").write_text(initial_code)
        (app_dir / "requirements.txt").write_text(FLASK_REQUIREMENTS)
        (app_dir / "Procfile").write_text(
            "web: flask --app app run --host 0.0.0.0 --port $PORT\n"
        )

        # Initialize and push
        init_git_repo(app_dir)
        add_hop3_remote(app_dir, hop3_container, app_name)
        result1 = git_push_to_hop3(app_dir, hop3_container)
        assert result1.returncode == 0, f"Initial push failed: {result1.stderr}"

        # Verify initial deployment succeeded
        combined_output1 = result1.stdout + result1.stderr
        assert "Deployment successful" in combined_output1, (
            "Expected 'Deployment successful' in initial push output"
        )

        # Verify initial source was extracted
        result = container.exec_run(f"cat /home/hop3/apps/{app_name}/src/app.py")
        assert "Version 1" in result.output.decode(), (
            "Initial version not found in deployed source"
        )

        # Modify code
        updated_code = """
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Version 2"
"""
        (app_dir / "app.py").write_text(updated_code)

        # Commit and push update
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        })
        subprocess.run(
            ["git", "add", "."],
            cwd=app_dir,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "commit", "-m", "Update to version 2"],
            cwd=app_dir,
            check=True,
            capture_output=True,
            env=env,
        )

        result2 = git_push_to_hop3(app_dir, hop3_container)
        assert result2.returncode == 0, f"Update push failed: {result2.stderr}"

        # Verify update deployment succeeded
        combined_output2 = result2.stdout + result2.stderr
        assert "Deployment successful" in combined_output2, (
            "Expected 'Deployment successful' in update push output"
        )

        # Verify updated source was extracted
        result = container.exec_run(f"cat /home/hop3/apps/{app_name}/src/app.py")
        assert "Version 2" in result.output.decode(), (
            "Updated version not found in deployed source"
        )

    def test_git_push_shows_deployment_output(
        self,
        hop3_container: dict[str, Any],
        git_test_app: Path,
    ):
        """
        Test that git push shows deployment progress to user.

        ARRANGE:
            - Create local git repository with Flask app

        ACT:
            - Push to hop3

        ASSERT:
            - Verify stderr contains deployment messages
            - Verify the app name appears in output
        """
        app_name = "git-push-output-test"

        add_hop3_remote(git_test_app, hop3_container, app_name)
        result = git_push_to_hop3(git_test_app, hop3_container)

        print(f"Push stdout:\n{result.stdout}")
        print(f"Push stderr:\n{result.stderr}")

        # Push should succeed
        assert result.returncode == 0

        # Output should contain deployment info (from post-receive hook)
        combined_output = result.stdout + result.stderr
        # Check for deployment-related output
        assert "Deployment" in combined_output or "deploy" in combined_output.lower(), (
            "Expected deployment output in push result"
        )
