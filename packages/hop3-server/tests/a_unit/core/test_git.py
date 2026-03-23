# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for git utilities."""

from __future__ import annotations

import pytest

from hop3.core.git import extract_app_name_from_repo_path


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
