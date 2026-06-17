# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for git-hook command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from hop3.commands.git import GitHookCmd
from hop3.orm import App


@pytest.fixture
def mock_app():
    """Create a mock app instance."""
    app = Mock(spec=App)
    app.name = "test-app"
    app.src_path = Path("/tmp/test-app/src")
    app.repo_path = Path("/tmp/test-app/repo")
    return app


@pytest.fixture
def mock_db_session(mock_app):
    """Create a mock database session."""
    session = Mock(spec=Session)
    app_repo = Mock()
    app_repo.get_one_or_none.return_value = mock_app

    with patch("hop3.commands.git.AppRepository", return_value=app_repo):
        yield session


@pytest.fixture
def git_hook_cmd(mock_db_session):
    """Create GitHookCmd instance."""
    return GitHookCmd(db_session=mock_db_session)


def test_git_hook_requires_app_name(git_hook_cmd):
    """Test that git-hook command requires an app name."""
    with pytest.raises(ValueError, match="Usage:"):
        git_hook_cmd.call()


def test_git_hook_app_not_found(git_hook_cmd):
    """Test error when app is not found."""
    with patch("hop3.commands.git.AppRepository") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.get_one_or_none.return_value = None

        result = git_hook_cmd.call("--app", "nonexistent-app")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]


def test_git_hook_no_stdin_data(git_hook_cmd, mock_app):
    """Test error when no push data is received."""
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = ""

        result = git_hook_cmd.call("--app", "test-app")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "No push data" in result[0]["text"]


def test_git_hook_invalid_push_data_format(git_hook_cmd, mock_app):
    """Test error with invalid push data format."""
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = "invalid data"

        result = git_hook_cmd.call("--app", "test-app")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "Invalid push data" in result[0]["text"]


def test_git_hook_successful_deployment(git_hook_cmd, mock_app, mock_db_session):
    """Test successful deployment from git push."""
    push_data = "aa453216d1b3e49e7f6f98441fa56946ddcd6a20 68f7abf4e6f922807889f52bc043ecd31b79f814 refs/heads/master"

    with (
        patch("sys.stdin") as mock_stdin,
        patch("hop3.commands.git.GitHookCmd._extract_commit_to_source") as mock_extract,
        patch("hop3.commands.git.do_deploy") as mock_deploy,
    ):
        mock_stdin.read.return_value = push_data

        result = git_hook_cmd.call("--app", "test-app")

        # Verify extraction was called with correct commit SHA
        mock_extract.assert_called_once_with(
            mock_app, "68f7abf4e6f922807889f52bc043ecd31b79f814"
        )

        # Verify deployment was triggered with app and db_session
        mock_deploy.assert_called_once_with(mock_app, db_session=mock_db_session)

        # Verify success response
        assert len(result) == 2
        assert "Deployment successful" in result[0]["text"]
        assert "68f7abf" in result[1]["text"]  # Should show short SHA


def test_extract_commit_to_source(git_hook_cmd, mock_app, tmp_path):
    """Test commit extraction from git repository."""
    # Setup temporary paths
    mock_app.src_path = tmp_path / "src"
    mock_app.repo_path = tmp_path / "repo"
    mock_app.repo_path.mkdir(parents=True)

    commit_sha = "68f7abf4e6f922807889f52bc043ecd31b79f814"

    with patch("subprocess.run") as mock_run, patch("shutil.rmtree"):
        # Mock successful subprocess calls
        mock_run.return_value = Mock(returncode=0)

        git_hook_cmd._extract_commit_to_source(mock_app, commit_sha)

        # Verify git archive was called
        archive_call = mock_run.call_args_list[0]
        assert "git" in archive_call[0][0]
        assert "archive" in archive_call[0][0]
        assert commit_sha in archive_call[0][0]
        assert archive_call[1]["cwd"] == mock_app.repo_path

        # Verify tar extraction was called
        tar_call = mock_run.call_args_list[1]
        assert "tar" in tar_call[0][0]
        assert "-xf" in tar_call[0][0]


def test_extract_commit_handles_multiple_refs(git_hook_cmd, mock_app):
    """Test handling of multiple refs in push data (processes first ref only)."""
    push_data = """aa453216d1b3e49e7f6f98441fa56946ddcd6a20 68f7abf4e6f922807889f52bc043ecd31b79f814 refs/heads/master
    bb563327e2c4f5af8g7g09552gb67057eecde7b25 79g8bcg5f7g033918900g63cd054fce42c80g925 refs/heads/develop"""

    with (
        patch("sys.stdin") as mock_stdin,
        patch("hop3.commands.git.GitHookCmd._extract_commit_to_source") as mock_extract,
        patch("hop3.commands.git.do_deploy"),
    ):
        mock_stdin.read.return_value = push_data

        git_hook_cmd.call("--app", "test-app")

        # Should process only the first ref (master)
        mock_extract.assert_called_once_with(
            mock_app, "68f7abf4e6f922807889f52bc043ecd31b79f814"
        )


def test_deployment_failure_handling(git_hook_cmd, mock_app):
    """Test error handling when deployment fails."""
    push_data = "aa453216d1b3e49e7f6f98441fa56946ddcd6a20 68f7abf4e6f922807889f52bc043ecd31b79f814 refs/heads/master"

    with (
        patch("sys.stdin") as mock_stdin,
        patch("hop3.commands.git.GitHookCmd._extract_commit_to_source"),
        patch("hop3.commands.git.do_deploy") as mock_deploy,
    ):
        mock_stdin.read.return_value = push_data
        mock_deploy.side_effect = Exception("Build failed: missing dependencies")

        # command_context raises ValueError for JSON-RPC error handling
        with pytest.raises(ValueError) as exc_info:
            git_hook_cmd.call("--app", "test-app")

        assert "missing dependencies" in str(exc_info.value)
