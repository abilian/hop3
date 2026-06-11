# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for server CLI git commands."""

from __future__ import annotations

from hop3.server.cli.git import GitReceivePackCmd, GitUploadPackCmd


class TestGitReceivePackCmd:
    """Test GitReceivePackCmd."""

    def test_command_name(self):
        """Test that command has correct name."""
        cmd = GitReceivePackCmd()
        assert cmd.name == "git-receive-pack"


class TestGitUploadPackCmd:
    """Test GitUploadPackCmd."""

    def test_command_name(self):
        """Test that command has correct name."""
        cmd = GitUploadPackCmd()
        assert cmd.name == "git-upload-pack"
