# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for git utilities."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hop3.core.git import (
    CLONE_MAX_BYTES,
    CloneTooLargeError,
    _run_capped,
    clone_repository,
    extract_app_name_from_repo_path,
)
from hop3.lib import CommandFailedError, CommandTimeoutError

if TYPE_CHECKING:
    from pathlib import Path


class TestExtractAppNameFromRepoPath:
    """Test extract_app_name_from_repo_path function."""

    def test_full_path_format(self):
        """Test extraction from /home/hop3/apps/<app>/git format."""
        assert extract_app_name_from_repo_path("/home/hop3/apps/myapp/git") == "myapp"
        assert (
            extract_app_name_from_repo_path("/home/hop3/apps/test-app/git")
            == "test-app"
        )

    def test_full_path_with_trailing_slash(self):
        """Test extraction from paths with trailing slash."""
        assert extract_app_name_from_repo_path("/home/hop3/apps/myapp/git/") == "myapp"

    def test_dotgit_format(self):
        """Test extraction from <app>.git format."""
        assert extract_app_name_from_repo_path("myapp.git") == "myapp"
        assert extract_app_name_from_repo_path("test-app.git") == "test-app"

    def test_plain_name_format(self):
        """Test extraction from plain <app> format."""
        assert extract_app_name_from_repo_path("myapp") == "myapp"
        assert extract_app_name_from_repo_path("test-app") == "test-app"

    def test_quoted_paths(self):
        """Test that quotes are stripped from paths."""
        assert extract_app_name_from_repo_path("'myapp'") == "myapp"
        assert extract_app_name_from_repo_path('"myapp"') == "myapp"
        assert extract_app_name_from_repo_path("'/home/hop3/apps/myapp/git'") == "myapp"

    def test_with_whitespace(self):
        """Test that whitespace is handled correctly."""
        assert extract_app_name_from_repo_path("  myapp  ") == "myapp"
        assert (
            extract_app_name_from_repo_path("  /home/hop3/apps/myapp/git  ") == "myapp"
        )

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/home/hop3/apps/flask-app/git", "flask-app"),
            ("/home/hop3/apps/node_app/git", "node_app"),
            ("my_app.git", "my_app"),
            ("my-app", "my-app"),
            ("'/home/hop3/apps/quoted-app/git'", "quoted-app"),
        ],
    )
    def test_various_app_names(self, path: str, expected: str):
        """Test various app name formats."""
        assert extract_app_name_from_repo_path(path) == expected


class TestCloneCaps:
    """
    The caps on `_run_capped`, which is what `clone_repository` runs git under.

    Exercised through cheap stand-in commands rather than a real clone: what is
    under test is that a runaway process is killed and reported, and a `sleep`
    or a `dd` reaches that path exactly as a git that will not finish does.
    """

    def test_a_process_that_outlives_the_timeout_is_killed(self, tmp_path: Path):
        with pytest.raises(CommandTimeoutError):
            _run_capped(
                ["sleep", "30"],
                watched=tmp_path,
                timeout=0.5,
                max_bytes=CLONE_MAX_BYTES,
            )

    def test_a_process_that_fills_the_directory_is_killed(self, tmp_path: Path):
        # Writes 4 MiB in 64 KiB steps, so the size walk sees it grow past a
        # 1 MiB cap while the process is still running.
        script = (
            f"for i in $(seq 1 64); do "
            f"dd if=/dev/zero of={tmp_path}/blob.$i bs=64k count=1 2>/dev/null; "
            f"sleep 0.05; done"
        )
        with pytest.raises(CloneTooLargeError) as exc_info:
            _run_capped(
                ["sh", "-c", script],
                watched=tmp_path,
                timeout=30,
                max_bytes=1024 * 1024,
            )
        assert "1048576 byte clone limit" in str(exc_info.value)

    def test_a_failing_process_carries_its_output(self, tmp_path: Path):
        with pytest.raises(CommandFailedError) as exc_info:
            _run_capped(
                ["sh", "-c", "echo 'repository not found' >&2; exit 128"],
                watched=tmp_path,
                timeout=30,
                max_bytes=CLONE_MAX_BYTES,
            )
        assert exc_info.value.returncode == 128
        assert "repository not found" in exc_info.value.stderr

    def test_a_process_that_exits_cleanly_is_not_disturbed(self, tmp_path: Path):
        _run_capped(
            ["sh", "-c", f"echo hello > {tmp_path}/file"],
            watched=tmp_path,
            timeout=30,
            max_bytes=CLONE_MAX_BYTES,
        )
        assert (tmp_path / "file").read_text() == "hello\n"


class TestCloneRepository:
    """`clone_repository` against real local repositories."""

    @staticmethod
    def _make_repo(path: Path) -> Path:
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(path)], check=True)
        (path / "README.md").write_text("hello\n")
        subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "x"],
            cwd=path,
            check=True,
        )
        return path

    def test_clones_a_repository(self, tmp_path: Path):
        source = self._make_repo(tmp_path / "source")
        dest = tmp_path / "dest"

        clone_repository(f"file://{source}", dest)

        assert (dest / "README.md").read_text() == "hello\n"

    def test_a_failed_clone_leaves_nothing_behind(self, tmp_path: Path):
        # The cap is worth nothing if the bytes it refused stay on the disk.
        dest = tmp_path / "dest"

        with pytest.raises(CommandFailedError):
            clone_repository(f"file://{tmp_path / 'no-such-repo'}", dest)

        assert not dest.exists()

    def test_it_refuses_a_destination_that_already_holds_something(
        self, tmp_path: Path
    ):
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "keep-me").write_text("data")

        with pytest.raises(FileExistsError):
            clone_repository("https://example.com/repo.git", dest)

        # And the pre-flight is what protects it: the cleanup path would
        # otherwise delete a directory this call never created.
        assert (dest / "keep-me").read_text() == "data"
