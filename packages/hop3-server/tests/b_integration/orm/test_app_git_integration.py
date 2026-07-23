# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for App.create() with git setup.

This module tests that App.create(setup_git=True) correctly initializes
git repositories for git push deployment.
"""

from __future__ import annotations

import shutil
import stat
from typing import TYPE_CHECKING

import pytest

from hop3.config import HopConfig
from hop3.orm import App

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session


@pytest.fixture
def configured_app_root(tmp_path: Path):
    """
    Configure HopConfig with a temporary root directory.

    Yields:
        Path to temporary HOP3_ROOT
    """
    HopConfig.reset_instance()
    test_config = HopConfig(hop3_root=tmp_path)
    HopConfig.set_instance(test_config)
    test_config.APP_ROOT.mkdir(parents=True, exist_ok=True)

    yield tmp_path

    HopConfig.reset_instance()


@pytest.mark.integration
class TestAppCreateWithGitSetup:
    """Integration tests for App.create() with setup_git parameter."""

    def test_create_without_git_setup(
        self, db_session: Session, configured_app_root: Path
    ):
        """
        Test that create() without setup_git doesn't initialize git.

        ARRANGE:
            - Create App instance

        ACT:
            - Call create() without setup_git parameter

        ASSERT:
            - Verify directories are created
            - Verify git repository is NOT initialized
        """
        app = App(name="no-git-app")
        db_session.add(app)
        db_session.commit()

        app.create(setup_git=False)

        # Verify directories exist
        assert app.app_path.exists()
        assert app.repo_path.exists()
        assert app.src_path.exists()

        # Verify git is NOT initialized
        assert not (app.repo_path / "HEAD").exists()

        # Cleanup
        shutil.rmtree(app.app_path)

    def test_create_with_git_setup_true(
        self, db_session: Session, configured_app_root: Path
    ):
        """
        Test that create(setup_git=True) initializes git repository.

        ARRANGE:
            - Create App instance

        ACT:
            - Call create(setup_git=True)

        ASSERT:
            - Verify directories are created
            - Verify bare git repository is initialized
            - Verify post-receive hook exists and is executable
        """
        app = App(name="git-enabled-app")
        db_session.add(app)
        db_session.commit()

        app.create(setup_git=True)

        # Verify directories exist
        assert app.app_path.exists()
        assert app.repo_path.exists()
        assert app.src_path.exists()
        assert app.data_path.exists()
        assert app.log_path.exists()

        # Verify bare git repository structure
        assert (app.repo_path / "HEAD").exists()
        assert (app.repo_path / "objects").exists()
        assert (app.repo_path / "refs").exists()

        # Verify post-receive hook
        hook_path = app.repo_path / "hooks" / "post-receive"
        assert hook_path.exists()
        assert hook_path.stat().st_mode & stat.S_IXUSR  # Executable

        # Verify hook content contains git-hook command
        hook_content = hook_path.read_text()
        assert "git-hook" in hook_content
        assert "git-enabled-app" in hook_content

        # Cleanup
        shutil.rmtree(app.app_path)

    def test_create_default_is_no_git_setup(
        self, db_session: Session, configured_app_root: Path
    ):
        """
        Test that create() defaults to NOT setting up git.

        ARRANGE:
            - Create App instance

        ACT:
            - Call create() without any parameters

        ASSERT:
            - Verify git is NOT initialized (backward compatible)
        """
        app = App(name="default-app")
        db_session.add(app)
        db_session.commit()

        app.create()  # No parameters

        # Verify git is NOT initialized (default behavior)
        assert not (app.repo_path / "HEAD").exists()

        # Cleanup
        shutil.rmtree(app.app_path)

    def test_create_with_git_setup_is_idempotent(
        self, db_session: Session, configured_app_root: Path
    ):
        """
        Test that calling create(setup_git=True) multiple times is safe.

        ARRANGE:
            - Create App instance

        ACT:
            - Call create(setup_git=True) twice

        ASSERT:
            - Verify no errors
            - Verify repository is still valid
        """
        app = App(name="idempotent-app")
        db_session.add(app)
        db_session.commit()

        # First create
        app.create(setup_git=True)
        assert (app.repo_path / "HEAD").exists()

        # Second create should not fail
        app.create(setup_git=True)
        assert (app.repo_path / "HEAD").exists()

        # Cleanup
        shutil.rmtree(app.app_path)

    def test_create_preserves_existing_repo(
        self, db_session: Session, configured_app_root: Path
    ):
        """
        Test that create(setup_git=True) preserves existing repository.

        ARRANGE:
            - Create App and initialize git with first commit

        ACT:
            - Add a test ref to the repository
            - Call create(setup_git=True) again

        ASSERT:
            - Verify the test ref still exists
        """
        app = App(name="preserve-repo-app")
        db_session.add(app)
        db_session.commit()

        app.create(setup_git=True)

        # Create a marker file to prove repo is preserved
        marker = app.repo_path / "test-marker"
        marker.write_text("test content")

        # Call create again
        app.create(setup_git=True)

        # Marker should still exist
        assert marker.exists()
        assert marker.read_text() == "test content"

        # Cleanup
        shutil.rmtree(app.app_path)
