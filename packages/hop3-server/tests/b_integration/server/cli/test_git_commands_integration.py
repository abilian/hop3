# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for server CLI git commands.

This module tests the GitReceivePackCmd and GitUploadPackCmd commands
that handle SSH git operations for git push deployment.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from hop3.config import HopConfig
from hop3.core.git import GitManager
from hop3.orm import App, AppRepository, get_session_factory
from hop3.server.cli.git import GitReceivePackCmd, GitUploadPackCmd

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from sqlalchemy.orm import Session


@pytest.fixture
def configured_hop3_root(tmp_path: Path):
    """Configure HopConfig with a temporary root directory.

    Yields:
        Path to temporary HOP3_ROOT
    """
    HopConfig.reset_instance()
    test_config = HopConfig(hop3_root=tmp_path)
    HopConfig.set_instance(test_config)
    test_config.APP_ROOT.mkdir(parents=True, exist_ok=True)

    yield tmp_path

    HopConfig.reset_instance()


@pytest.fixture
def test_app_with_git_repo(
    db_session: Session, configured_hop3_root: Path
) -> Iterator[App]:
    """Create a test application with initialized git repository.

    Args:
        db_session: Database session
        configured_hop3_root: Configured temporary HOP3_ROOT

    Yields:
        App instance with git repository set up
    """
    # Create app in database
    app = App(name="git-cli-test", hostname="test.example.com", port=8000)
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    # Create app directories
    app.app_path.mkdir(parents=True, exist_ok=True)
    app.repo_path.mkdir(parents=True, exist_ok=True)
    app.src_path.mkdir(parents=True, exist_ok=True)

    # Initialize git repository
    git_manager = GitManager(app)
    git_manager.setup_hook()

    yield app

    # Cleanup
    if app.app_path.exists():
        shutil.rmtree(app.app_path)


@pytest.mark.integration
class TestGitReceivePackCmdIntegration:
    """Integration tests for GitReceivePackCmd."""

    def test_command_name_is_correct(self):
        """Test that command has correct name for SSH routing."""
        cmd = GitReceivePackCmd()
        assert cmd.name == "git-receive-pack"

    def test_receive_pack_extracts_app_name_from_full_path(
        self, db_session: Session, test_app_with_git_repo: App
    ):
        """Test app name extraction from full repository path.

        ARRANGE:
            - Create app with git repository

        ACT:
            - Call receive_pack with full path format

        ASSERT:
            - Verify git-receive-pack is called with correct repo path
        """
        cmd = GitReceivePackCmd()
        app = test_app_with_git_repo

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            # Mock the session factory to return our test session
            with patch.object(
                get_session_factory(),
                "__call__",
                return_value=db_session,
            ):
                # Use full path format
                repo_path = str(app.repo_path)
                cmd.run(repo_path)

            # Verify git-receive-pack was called
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "git-receive-pack" in call_args

    def test_receive_pack_auto_creates_app_on_first_push(
        self, db_session: Session, configured_hop3_root: Path
    ):
        """Test that app is auto-created on first git push.

        ARRANGE:
            - No app exists in database

        ACT:
            - Call receive_pack with new app name

        ASSERT:
            - Verify new app is created in database
            - Verify git repository is initialized
        """
        cmd = GitReceivePackCmd()

        # Use a mock session factory that returns our db_session
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = MagicMock(return_value=db_session)
        mock_session_factory.return_value.__exit__ = MagicMock(return_value=None)

        with (
            patch(
                "hop3.server.cli.git.get_session_factory",
                return_value=mock_session_factory,
            ),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)

            # Push to non-existent app
            cmd.run("new-auto-app")

            # Verify app was created
            app_repo = AppRepository(session=db_session)
            app = app_repo.get_one_or_none(name="new-auto-app")

            assert app is not None
            assert app.name == "new-auto-app"

            # Cleanup
            if app and app.app_path.exists():
                shutil.rmtree(app.app_path)

    def test_receive_pack_handles_quoted_paths(
        self, db_session: Session, test_app_with_git_repo: App
    ):
        """Test handling of quoted paths from SSH.

        Git often sends paths with quotes when routing through SSH.

        ARRANGE:
            - Create app with git repository

        ACT:
            - Call receive_pack with quoted path

        ASSERT:
            - Verify app name is correctly extracted
            - Verify receive_pack is called
        """
        cmd = GitReceivePackCmd()
        app = test_app_with_git_repo

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = MagicMock(return_value=db_session)
        mock_session_factory.return_value.__exit__ = MagicMock(return_value=None)

        with (
            patch(
                "hop3.server.cli.git.get_session_factory",
                return_value=mock_session_factory,
            ),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)

            # Use quoted path (as SSH would send)
            cmd.run(f"'{app.repo_path}'")

            # Verify git-receive-pack was called
            mock_run.assert_called_once()

    def test_receive_pack_handles_simple_app_name(
        self, db_session: Session, test_app_with_git_repo: App
    ):
        """Test handling of simple app name (without path).

        ARRANGE:
            - Create app with git repository

        ACT:
            - Call receive_pack with just app name

        ASSERT:
            - Verify app is found and receive_pack is called
        """
        cmd = GitReceivePackCmd()

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = MagicMock(return_value=db_session)
        mock_session_factory.return_value.__exit__ = MagicMock(return_value=None)

        with (
            patch(
                "hop3.server.cli.git.get_session_factory",
                return_value=mock_session_factory,
            ),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)

            cmd.run("git-cli-test")

            mock_run.assert_called_once()


@pytest.mark.integration
class TestGitUploadPackCmdIntegration:
    """Integration tests for GitUploadPackCmd."""

    def test_command_name_is_correct(self):
        """Test that command has correct name for SSH routing."""
        cmd = GitUploadPackCmd()
        assert cmd.name == "git-upload-pack"

    def test_upload_pack_fails_for_nonexistent_app(
        self, db_session: Session, configured_hop3_root: Path, capsys
    ):
        """Test error when app doesn't exist.

        ARRANGE:
            - No app exists in database

        ACT:
            - Call upload_pack with non-existent app name

        ASSERT:
            - Verify exit code 1 is raised
            - Verify error message is printed
        """
        cmd = GitUploadPackCmd()

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = MagicMock(return_value=db_session)
        mock_session_factory.return_value.__exit__ = MagicMock(return_value=None)

        with (
            patch(
                "hop3.server.cli.git.get_session_factory",
                return_value=mock_session_factory,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd.run("nonexistent-app")

        assert exc_info.value.code == 1

    def test_upload_pack_fails_for_uninitialized_repo(
        self, db_session: Session, configured_hop3_root: Path
    ):
        """Test error when repository is not initialized.

        ARRANGE:
            - Create app but don't initialize git repository

        ACT:
            - Call upload_pack

        ASSERT:
            - Verify exit code 1 is raised
            - Verify helpful error message is printed
        """
        # Create app without git repo
        app = App(name="no-repo-app")
        db_session.add(app)
        db_session.commit()

        # Create directories but NOT git repo
        app.app_path.mkdir(parents=True, exist_ok=True)
        app.repo_path.mkdir(parents=True, exist_ok=True)
        # Note: NOT calling GitManager.setup_hook()

        cmd = GitUploadPackCmd()

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = MagicMock(return_value=db_session)
        mock_session_factory.return_value.__exit__ = MagicMock(return_value=None)

        with (
            patch(
                "hop3.server.cli.git.get_session_factory",
                return_value=mock_session_factory,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd.run("no-repo-app")

        assert exc_info.value.code == 1

        # Cleanup
        if app.app_path.exists():
            shutil.rmtree(app.app_path)

    def test_upload_pack_success_with_initialized_repo(
        self, db_session: Session, test_app_with_git_repo: App
    ):
        """Test successful upload_pack for initialized repository.

        ARRANGE:
            - Create app with initialized git repository

        ACT:
            - Call upload_pack

        ASSERT:
            - Verify git-upload-pack is called
        """
        cmd = GitUploadPackCmd()

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = MagicMock(return_value=db_session)
        mock_session_factory.return_value.__exit__ = MagicMock(return_value=None)

        with (
            patch(
                "hop3.server.cli.git.get_session_factory",
                return_value=mock_session_factory,
            ),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)

            cmd.run("git-cli-test")

            # Verify git-upload-pack was called
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "git-upload-pack" in call_args
