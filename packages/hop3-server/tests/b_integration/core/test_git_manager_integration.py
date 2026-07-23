# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for GitManager.

This module tests GitManager functionality including:
- Bare repository initialization
- Post-receive hook setup
- Lazy initialization in receive_pack()
- upload_pack functionality
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from hop3.config import HopConfig
from hop3.core.git import GitManager
from hop3.orm import App

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from sqlalchemy.orm import Session


@pytest.fixture
def configured_git_root(tmp_path: Path):
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


@pytest.fixture
def test_app(db_session: Session, configured_git_root: Path) -> Iterator[App]:
    """
    Create a test application with directories.

    Yields:
        App instance with directories set up
    """
    app = App(name="git-manager-test", hostname="test.example.com", port=8000)
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    # Create directories but don't initialize git
    app.app_path.mkdir(parents=True, exist_ok=True)
    app.repo_path.mkdir(parents=True, exist_ok=True)
    app.src_path.mkdir(parents=True, exist_ok=True)

    yield app

    # Cleanup
    if app.app_path.exists():
        shutil.rmtree(app.app_path)


@pytest.mark.integration
class TestGitManagerSetupHook:
    """Integration tests for GitManager.setup_hook()."""

    def test_setup_hook_initializes_bare_repo(self, db_session: Session, test_app: App):
        """
        Test that setup_hook() creates a bare git repository.

        ARRANGE:
            - Create app with empty repo_path directory

        ACT:
            - Call GitManager.setup_hook()

        ASSERT:
            - Verify bare repository structure (HEAD, objects, refs)
        """
        git_manager = GitManager(test_app)

        git_manager.setup_hook()

        # Verify bare repo structure
        assert (test_app.repo_path / "HEAD").exists()
        assert (test_app.repo_path / "objects").exists()
        assert (test_app.repo_path / "refs").exists()
        assert (test_app.repo_path / "refs" / "heads").exists()

    def test_setup_hook_creates_post_receive_hook(
        self, db_session: Session, test_app: App
    ):
        """
        Test that setup_hook() creates post-receive hook.

        ARRANGE:
            - Create app with empty repo_path directory

        ACT:
            - Call GitManager.setup_hook()

        ASSERT:
            - Verify post-receive hook exists
            - Verify hook is executable
            - Verify hook content is correct
        """
        git_manager = GitManager(test_app)

        git_manager.setup_hook()

        hook_path = test_app.repo_path / "hooks" / "post-receive"

        # Verify hook exists and is executable
        assert hook_path.exists()
        assert hook_path.stat().st_mode & stat.S_IXUSR

        # Verify hook content
        hook_content = hook_path.read_text()
        assert "bash" in hook_content  # Either #!/bin/bash or #!/usr/bin/env bash
        assert "git-hook" in hook_content
        assert test_app.name in hook_content

    def test_setup_hook_is_idempotent(self, db_session: Session, test_app: App):
        """
        Test that calling setup_hook() multiple times is safe.

        ARRANGE:
            - Create app

        ACT:
            - Call setup_hook() twice

        ASSERT:
            - Verify no errors
            - Verify repository still valid
        """
        git_manager = GitManager(test_app)

        # First call
        git_manager.setup_hook()
        assert (test_app.repo_path / "HEAD").exists()

        # Second call should not fail
        git_manager.setup_hook()
        assert (test_app.repo_path / "HEAD").exists()

    def test_setup_hook_preserves_existing_content(
        self, db_session: Session, test_app: App
    ):
        """
        Test that setup_hook() preserves existing repository content.

        ARRANGE:
            - Initialize repository
            - Add a marker file

        ACT:
            - Call setup_hook() again

        ASSERT:
            - Verify marker file still exists
        """
        git_manager = GitManager(test_app)

        # First setup
        git_manager.setup_hook()

        # Add marker
        marker = test_app.repo_path / "test-marker"
        marker.write_text("preserved")

        # Second setup
        git_manager.setup_hook()

        # Marker should be preserved
        assert marker.exists()
        assert marker.read_text() == "preserved"


@pytest.mark.integration
class TestGitManagerReceivePack:
    """Integration tests for GitManager.receive_pack()."""

    def test_receive_pack_lazy_initializes_repo(
        self, db_session: Session, test_app: App
    ):
        """
        Test that receive_pack() initializes repo if not exists.

        ARRANGE:
            - Create app with no git repository

        ACT:
            - Call receive_pack()

        ASSERT:
            - Verify repository is initialized before git-receive-pack runs
        """
        git_manager = GitManager(test_app)

        # Verify repo not initialized
        assert not (test_app.repo_path / "HEAD").exists()

        original_run = subprocess.run
        receive_pack_called = False

        def mock_run(cmd, *args, **kwargs):
            nonlocal receive_pack_called
            # Let git init and other setup commands run normally
            # Only mock git-receive-pack (which expects stdin/stdout from git client)
            if cmd and "git-receive-pack" in cmd:
                receive_pack_called = True
                return MagicMock(returncode=0)
            return original_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            git_manager.receive_pack()

        # Verify repo was initialized (by the real git init --bare)
        assert (test_app.repo_path / "HEAD").exists()

        # Verify git-receive-pack was called
        assert receive_pack_called

    def test_receive_pack_skips_init_if_repo_exists(
        self, db_session: Session, test_app: App
    ):
        """
        Test that receive_pack() doesn't reinitialize existing repo.

        ARRANGE:
            - Create app with initialized git repository
            - Add a marker file

        ACT:
            - Call receive_pack()

        ASSERT:
            - Verify marker file still exists (repo not reinitialized)
        """
        git_manager = GitManager(test_app)

        # Initialize repo first
        git_manager.setup_hook()

        # Add marker
        marker = test_app.repo_path / "test-marker"
        marker.write_text("preserved")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            git_manager.receive_pack()

        # Marker should be preserved
        assert marker.exists()

    def test_receive_pack_calls_git_receive_pack(
        self, db_session: Session, test_app: App
    ):
        """
        Test that receive_pack() calls git-receive-pack command.

        ARRANGE:
            - Create app with initialized git repository

        ACT:
            - Call receive_pack()

        ASSERT:
            - Verify git-receive-pack is called with correct path
        """
        git_manager = GitManager(test_app)
        git_manager.setup_hook()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            git_manager.receive_pack()

            mock_run.assert_called_once()
            call_args = mock_run.call_args

            # Verify command
            assert call_args[0][0] == ["git-receive-pack", str(test_app.repo_path)]

            # Verify cwd is set to repo_path
            assert call_args[1]["cwd"] == test_app.repo_path


@pytest.mark.integration
class TestGitManagerUploadPack:
    """Integration tests for GitManager.upload_pack()."""

    def test_upload_pack_calls_git_upload_pack(
        self, db_session: Session, test_app: App
    ):
        """
        Test that upload_pack() calls git-upload-pack command.

        ARRANGE:
            - Create app with initialized git repository

        ACT:
            - Call upload_pack()

        ASSERT:
            - Verify git-upload-pack is called with correct path
        """
        git_manager = GitManager(test_app)
        git_manager.setup_hook()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            git_manager.upload_pack()

            mock_run.assert_called_once()
            call_args = mock_run.call_args

            # Verify command
            assert call_args[0][0] == ["git-upload-pack", str(test_app.repo_path)]


@pytest.mark.integration
class TestGitManagerProperties:
    """Integration tests for GitManager properties."""

    def test_app_name_property(self, db_session: Session, test_app: App):
        """Test that app_name property returns correct name."""
        git_manager = GitManager(test_app)
        assert git_manager.app_name == "git-manager-test"

    def test_repo_path_property(self, db_session: Session, test_app: App):
        """Test that repo_path property returns correct path."""
        git_manager = GitManager(test_app)
        assert git_manager.repo_path == test_app.repo_path
