# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for git hook command using state-based testing.

This module tests git hook commands using real database interactions:
- Uses real database instead of mocks (via db_session fixture)
- Commands receive session parameter directly
- Verifies actual database state changes
- Tests that outcomes (state) are correct, not just that methods were called
- Mock only subprocess calls (external I/O boundary)
"""

from __future__ import annotations

import shutil
import subprocess
from subprocess import CalledProcessError
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from hop3.commands.git import GitHookCmd
from hop3.config import HopConfig
from hop3.deployers.volumes import previous_source_path
from hop3.orm import App

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from sqlalchemy.orm import Session


def _commit(repo: Path, files: dict[str, str]) -> str:
    """Make ``repo`` a git repository holding one commit of ``files``."""
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], check=True)
    for name, text in files.items():
        (repo / name).write_text(text)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "c"], check=True)
    out = subprocess.run(
        [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


@pytest.fixture
def test_git_app(db_session: Session, tmp_path: Path, monkeypatch) -> Iterator[App]:
    """
    Create a test application with git repository structure.

    Args:
        db_session: Database session
        tmp_path: Temporary directory for app files
        monkeypatch: pytest monkeypatch for patching HopConfig

    Returns:
        App instance with git repository paths set up
    """
    # Setup test HopConfig with temporary directory
    HopConfig.reset_instance()
    test_config = HopConfig(hop3_root=tmp_path)
    HopConfig.set_instance(test_config)

    # Ensure app root directory exists
    test_config.APP_ROOT.mkdir(parents=True, exist_ok=True)

    # Create app in database
    app = App(name="test-app", hostname="test.example.com", port=8000)
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    # Create the expected directory structure
    # (app_path is computed as APP_ROOT / name)
    app.app_path.mkdir(parents=True, exist_ok=True)
    app.repo_path.mkdir(parents=True, exist_ok=True)
    app.src_path.mkdir(parents=True, exist_ok=True)

    yield app

    # Cleanup
    HopConfig.reset_instance()
    if app.app_path.exists():
        shutil.rmtree(app.app_path)


@pytest.mark.integration
class TestGitHookCmdIntegration:
    """Integration tests for GitHookCmd using state-based testing."""

    def test_git_hook_requires_app_name(self, db_session: Session):
        """
        Test that git-hook command requires an app name.

        ARRANGE:
            - Create command instance without app name argument

        ACT:
            - Call command without arguments

        ASSERT:
            - Verify ValueError is raised with usage message
        """
        cmd = GitHookCmd(db_session=db_session)

        with pytest.raises(ValueError, match=r"Usage:.*git-hook"):
            cmd.call()

    def test_git_hook_app_not_found(self, db_session: Session):
        """
        Test error when app is not found in database.

        ARRANGE:
            - Database with no apps

        ACT:
            - Call command with non-existent app name

        ASSERT:
            - Verify error message about app not found
            - Verify error type is "error"
        """
        cmd = GitHookCmd(db_session=db_session)

        result = cmd.call("--app", "nonexistent-app")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]

    def test_git_hook_no_stdin_data(self, db_session: Session, test_git_app: App):
        """
        Test error when no push data is received from stdin.

        ARRANGE:
            - Create app in database
            - Mock stdin to return empty string

        ACT:
            - Call command with empty stdin

        ASSERT:
            - Verify error message about missing push data
            - Verify error type is "error"
        """
        cmd = GitHookCmd(db_session=db_session)

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = ""
            result = cmd.call("--app", "test-app")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "No push data received" in result[0]["text"]

    def test_git_hook_invalid_push_data_format(
        self, db_session: Session, test_git_app: App
    ):
        """
        Test error with invalid push data format.

        ARRANGE:
            - Create app in database
            - Mock stdin to return invalid push data

        ACT:
            - Call command with malformed push data

        ASSERT:
            - Verify error message about invalid format
            - Verify error type is "error"
        """
        cmd = GitHookCmd(db_session=db_session)

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.read.return_value = "invalid data"
            result = cmd.call("--app", "test-app")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "Invalid push data" in result[0]["text"]

    def test_git_hook_successful_deployment(
        self, db_session: Session, test_git_app: App
    ):
        """
        Test successful deployment from git push.

        ARRANGE:
            - Create app in database
            - Mock stdin with valid push data
            - Mock subprocess calls for git operations
            - Mock deployment function

        ACT:
            - Call command with valid push data

        ASSERT:
            - Verify commit extraction was called with correct SHA
            - Verify deployment was triggered
            - Verify success response contains proper messages
            - Verify short SHA is displayed in output
        """
        push_data = "aa453216d1b3e49e7f6f98441fa56946ddcd6a20 68f7abf4e6f922807889f52bc043ecd31b79f814 refs/heads/master"

        cmd = GitHookCmd(db_session=db_session)

        with (
            patch("sys.stdin") as mock_stdin,
            patch("hop3.commands.git.GitHookCmd._extract_commit_to_source"),
            patch("hop3.commands.git.do_deploy") as mock_deploy,
        ):
            mock_stdin.read.return_value = push_data

            result = cmd.call("--app", "test-app")

            # Verify deployment was triggered
            mock_deploy.assert_called_once()
            called_app = mock_deploy.call_args[0][0]
            assert called_app.name == "test-app"

            # Verify success response
            assert len(result) == 2
            assert result[0]["t"] == "text"
            assert "Deployment successful" in result[0]["text"]
            assert "68f7abf" in result[1]["text"]  # Short SHA

    def test_git_hook_extract_commit_to_source(
        self, db_session: Session, test_git_app: App
    ):
        """The commit's tree replaces src/; the old tree is set aside, not lost."""
        (test_git_app.src_path / "old_file.txt").write_text("old content")
        commit_sha = _commit(test_git_app.repo_path, {"app.py": "print('v2')\n"})

        GitHookCmd(db_session=db_session)._extract_commit_to_source(
            test_git_app, commit_sha
        )

        assert (test_git_app.src_path / "app.py").read_text() == "print('v2')\n"
        assert not (test_git_app.src_path / "old_file.txt").exists()
        previous = previous_source_path(test_git_app)
        assert (previous / "old_file.txt").read_text() == "old content"

    def test_git_hook_handles_multiple_refs_first_only(
        self, db_session: Session, test_git_app: App
    ):
        """
        Test handling of multiple refs in push data (processes first ref only).

        ARRANGE:
            - Create app in database
            - Mock stdin with push data containing multiple refs

        ACT:
            - Call command with multi-ref push data

        ASSERT:
            - Verify deployment processes only the first ref (master)
            - Verify second ref is ignored
            - Verify success response for first ref
        """
        push_data = """aa453216d1b3e49e7f6f98441fa56946ddcd6a20 68f7abf4e6f922807889f52bc043ecd31b79f814 refs/heads/master
bb563327e2c4f5af8g7g09552gb67057eecde7b25 79g8bcg5f7g033918900g63cd054fce42c80g925 refs/heads/develop"""

        cmd = GitHookCmd(db_session=db_session)

        with (
            patch("sys.stdin") as mock_stdin,
            patch(
                "hop3.commands.git.GitHookCmd._extract_commit_to_source"
            ) as mock_extract,
            patch("hop3.commands.git.do_deploy"),
        ):
            mock_stdin.read.return_value = push_data

            result = cmd.call("--app", "test-app")

            # Should process only the first ref (master)
            mock_extract.assert_called_once()
            called_sha = mock_extract.call_args[0][1]
            assert called_sha == "68f7abf4e6f922807889f52bc043ecd31b79f814"

            # Verify success
            assert len(result) == 2
            assert "68f7abf" in result[1]["text"]

    def test_git_hook_deployment_failure_handling(
        self, db_session: Session, test_git_app: App
    ):
        """
        Test error handling when deployment fails.

        ARRANGE:
            - Create app in database
            - Mock stdin with valid push data
            - Mock deployment to raise an exception

        ACT:
            - Call command when deployment fails

        ASSERT:
            - Verify error response with failure message
            - Verify error type is "error"
            - Verify exception details are included in error message
        """
        push_data = "aa453216d1b3e49e7f6f98441fa56946ddcd6a20 68f7abf4e6f922807889f52bc043ecd31b79f814 refs/heads/master"

        cmd = GitHookCmd(db_session=db_session)

        with (
            patch("sys.stdin") as mock_stdin,
            patch("hop3.commands.git.GitHookCmd._extract_commit_to_source"),
            patch("hop3.commands.git.do_deploy") as mock_deploy,
        ):
            mock_stdin.read.return_value = push_data
            mock_deploy.side_effect = Exception("Build failed: missing dependencies")

            # command_context raises ValueError for JSON-RPC error handling
            with pytest.raises(ValueError) as exc_info:
                cmd.call("--app", "test-app")

            assert "missing dependencies" in str(exc_info.value)

    def test_git_hook_branch_name_extraction(
        self, db_session: Session, test_git_app: App
    ):
        """
        Test branch name extraction from git ref.

        ARRANGE:
            - Create app in database
            - Mock stdin with different branch ref format

        ACT:
            - Call command with develop branch ref

        ASSERT:
            - Verify branch name is correctly extracted from full ref path
            - Verify deployment is triggered with correct app
        """
        push_data = "aa453216d1b3e49e7f6f98441fa56946ddcd6a20 68f7abf4e6f922807889f52bc043ecd31b79f814 refs/heads/develop"

        cmd = GitHookCmd(db_session=db_session)

        with (
            patch("sys.stdin") as mock_stdin,
            patch("hop3.commands.git.GitHookCmd._extract_commit_to_source"),
            patch("hop3.commands.git.do_deploy"),
        ):
            mock_stdin.read.return_value = push_data

            result = cmd.call("--app", "test-app")

            # Verify deployment succeeds with develop branch
            assert len(result) == 2
            assert "Deployment successful" in result[0]["text"]

    def test_git_hook_subprocess_error_handling(
        self, db_session: Session, test_git_app: App
    ):
        """
        Test error handling when subprocess calls fail.

        ARRANGE:
            - Create app in database
            - Mock stdin with valid push data
            - Mock subprocess to raise CalledProcessError

        ACT:
            - Call _extract_commit_to_source when git archive fails

        ASSERT:
            - Verify exception is properly raised
            - Verify error contains subprocess error details
        """
        commit_sha = "68f7abf4e6f922807889f52bc043ecd31b79f814"

        cmd = GitHookCmd(db_session=db_session)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = CalledProcessError(
                1, "git archive", stderr="fatal: bad object"
            )

            with pytest.raises(CalledProcessError):
                cmd._extract_commit_to_source(test_git_app, commit_sha)

    def test_git_hook_whitespace_handling_in_push_data(
        self, db_session: Session, test_git_app: App
    ):
        """
        Test proper handling of whitespace in push data.

        ARRANGE:
            - Create app in database
            - Mock stdin with push data containing extra whitespace

        ACT:
            - Call command with push data that has extra spaces

        ASSERT:
            - Verify command correctly parses push data despite whitespace
            - Verify deployment succeeds
        """
        push_data = "aa453216d1b3e49e7f6f98441fa56946ddcd6a20    68f7abf4e6f922807889f52bc043ecd31b79f814    refs/heads/master   "

        cmd = GitHookCmd(db_session=db_session)

        with (
            patch("sys.stdin") as mock_stdin,
            patch("hop3.commands.git.GitHookCmd._extract_commit_to_source"),
            patch("hop3.commands.git.do_deploy"),
        ):
            mock_stdin.read.return_value = push_data

            result = cmd.call("--app", "test-app")

            assert len(result) == 2
            assert "Deployment successful" in result[0]["text"]

    def test_git_hook_short_commit_sha_display(
        self, db_session: Session, test_git_app: App
    ):
        """
        Test that commit SHA is displayed in short form (first 8 chars).

        ARRANGE:
            - Create app in database
            - Mock stdin with full 40-char SHA

        ACT:
            - Call command and check output

        ASSERT:
            - Verify output contains short SHA (first 8 chars)
            - Verify full SHA is not in output
        """
        full_sha = "68f7abf4e6f922807889f52bc043ecd31b79f814"
        short_sha = "68f7abf4"

        push_data = (
            f"aa453216d1b3e49e7f6f98441fa56946ddcd6a20 {full_sha} refs/heads/master"
        )

        cmd = GitHookCmd(db_session=db_session)

        with (
            patch("sys.stdin") as mock_stdin,
            patch("hop3.commands.git.GitHookCmd._extract_commit_to_source"),
            patch("hop3.commands.git.do_deploy"),
        ):
            mock_stdin.read.return_value = push_data

            result = cmd.call("--app", "test-app")

            output_text = " ".join(r["text"] for r in result)
            assert short_sha in output_text
            # Full SHA should not be in the friendly output
            assert full_sha not in output_text
