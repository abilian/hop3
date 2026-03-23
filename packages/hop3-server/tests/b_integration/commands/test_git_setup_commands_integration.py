# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for git:setup command.

This module tests the GitSetupCmd RPC command that sets up
git push deployment for an application.
"""

from __future__ import annotations

import shutil
import stat
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from hop3.commands.git import GitSetupCmd
from hop3.config import HopConfig
from hop3.orm import App

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session


@pytest.fixture
def test_app_for_git(db_session: Session, tmp_path: Path) -> App:
    """Create a test application for git setup tests.

    Args:
        db_session: Database session
        tmp_path: Temporary directory for app files

    Returns:
        App instance with directories set up
    """
    # Setup test HopConfig with temporary directory
    HopConfig.reset_instance()
    test_config = HopConfig(hop3_root=tmp_path)
    HopConfig.set_instance(test_config)

    # Ensure app root directory exists
    test_config.APP_ROOT.mkdir(parents=True, exist_ok=True)

    # Create app in database
    app = App(name="git-test-app", hostname="git-test.example.com", port=8000)
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    # Create the expected directory structure
    app.app_path.mkdir(parents=True, exist_ok=True)
    app.repo_path.mkdir(parents=True, exist_ok=True)
    app.src_path.mkdir(parents=True, exist_ok=True)

    yield app

    # Cleanup
    HopConfig.reset_instance()
    if app.app_path.exists():
        shutil.rmtree(app.app_path)


@pytest.mark.integration
class TestGitSetupCmdIntegration:
    """Integration tests for GitSetupCmd."""

    def test_git_setup_requires_app_name(self, db_session: Session):
        """Test that git:setup command requires an app name.

        ARRANGE:
            - Create command instance without app name argument

        ACT:
            - Call command without arguments

        ASSERT:
            - Verify ValueError is raised with usage message
        """
        cmd = GitSetupCmd(db_session=db_session)

        with pytest.raises(ValueError, match=r"Usage:.*git:setup"):
            cmd.call()

    def test_git_setup_app_not_found(self, db_session: Session):
        """Test error when app is not found in database.

        ARRANGE:
            - Database with no apps

        ACT:
            - Call command with non-existent app name

        ASSERT:
            - Verify ValueError is raised about app not found
        """
        cmd = GitSetupCmd(db_session=db_session)

        with pytest.raises(ValueError, match=r"not found"):
            cmd.call("nonexistent-app")

    def test_git_setup_success(self, db_session: Session, test_app_for_git: App):
        """Test successful git setup for an app.

        ARRANGE:
            - Create app in database with directories

        ACT:
            - Call git:setup command

        ASSERT:
            - Verify success message is returned
            - Verify git remote URL is displayed
            - Verify instructions are provided
        """
        cmd = GitSetupCmd(db_session=db_session)

        with patch("hop3.core.git.GitManager.setup_hook") as mock_setup:
            result = cmd.call("git-test-app")

        # Verify setup_hook was called
        mock_setup.assert_called_once()

        # Verify response structure
        assert len(result) >= 3

        # First message should be success
        assert result[0]["t"] == "success"
        assert "Git deployment enabled" in result[0]["text"]
        assert "git-test-app" in result[0]["text"]

        # Should contain git remote add instructions
        result_text = " ".join(r.get("text", "") for r in result)
        assert "git remote add" in result_text
        assert "git push hop3 main" in result_text

    def test_git_setup_uses_app_hostname(
        self, db_session: Session, test_app_for_git: App
    ):
        """Test that git:setup uses app's hostname in git URL.

        ARRANGE:
            - Create app with specific hostname

        ACT:
            - Call git:setup command

        ASSERT:
            - Verify git URL uses the app's hostname
        """
        cmd = GitSetupCmd(db_session=db_session)

        with patch("hop3.core.git.GitManager.setup_hook"):
            result = cmd.call("git-test-app")

        # Join all result text
        result_text = " ".join(r.get("text", "") for r in result)

        # Should use the app's hostname
        assert "git-test.example.com" in result_text
        assert "hop3@git-test.example.com:git-test-app" in result_text

    def test_git_setup_falls_back_to_socket_hostname(
        self, db_session: Session, tmp_path: Path
    ):
        """Test that git:setup falls back to socket.gethostname() if no app hostname.

        ARRANGE:
            - Create app without hostname

        ACT:
            - Call git:setup command

        ASSERT:
            - Verify git URL uses socket.gethostname()
        """
        # Setup test HopConfig
        HopConfig.reset_instance()
        test_config = HopConfig(hop3_root=tmp_path)
        HopConfig.set_instance(test_config)
        test_config.APP_ROOT.mkdir(parents=True, exist_ok=True)

        # Create app without hostname
        app = App(name="no-hostname-app")
        db_session.add(app)
        db_session.commit()

        # Create directories
        app.app_path.mkdir(parents=True, exist_ok=True)
        app.repo_path.mkdir(parents=True, exist_ok=True)

        cmd = GitSetupCmd(db_session=db_session)

        with (
            patch("hop3.core.git.GitManager.setup_hook"),
            patch("socket.gethostname", return_value="test-server.local"),
        ):
            result = cmd.call("no-hostname-app")

        # Join all result text
        result_text = " ".join(r.get("text", "") for r in result)

        # Should use socket hostname
        assert "test-server.local" in result_text

        # Cleanup
        HopConfig.reset_instance()
        if app.app_path.exists():
            shutil.rmtree(app.app_path)

    def test_git_setup_creates_bare_repository(
        self, db_session: Session, test_app_for_git: App
    ):
        """Test that git:setup creates a bare git repository.

        ARRANGE:
            - Create app with directories but no git repo

        ACT:
            - Call git:setup command (without mocking setup_hook)

        ASSERT:
            - Verify bare repository is created
            - Verify HEAD file exists
            - Verify post-receive hook is created
        """
        cmd = GitSetupCmd(db_session=db_session)

        # Don't mock setup_hook to test actual behavior
        result = cmd.call("git-test-app")

        # Verify success
        assert result[0]["t"] == "success"

        # Verify bare repository structure
        assert test_app_for_git.repo_path.exists()
        assert (test_app_for_git.repo_path / "HEAD").exists()
        assert (test_app_for_git.repo_path / "hooks" / "post-receive").exists()

        # Verify hook is executable
        hook_path = test_app_for_git.repo_path / "hooks" / "post-receive"
        assert hook_path.stat().st_mode & stat.S_IXUSR

    def test_git_setup_idempotent(self, db_session: Session, test_app_for_git: App):
        """Test that running git:setup multiple times is safe.

        ARRANGE:
            - Create app with directories

        ACT:
            - Call git:setup twice

        ASSERT:
            - Verify both calls succeed
            - Verify repository still works after second call
        """
        cmd = GitSetupCmd(db_session=db_session)

        # First call
        result1 = cmd.call("git-test-app")
        assert result1[0]["t"] == "success"

        # Second call should also succeed (idempotent)
        result2 = cmd.call("git-test-app")
        assert result2[0]["t"] == "success"

        # Repository should still be valid
        assert (test_app_for_git.repo_path / "HEAD").exists()
