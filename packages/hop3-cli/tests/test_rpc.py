# Copyright (c) 2025, Abilian SAS
"""
Misc tests for the RPC client.
"""

from __future__ import annotations

from hop3_cli.main import get_extra_args


def test_extra_args():
    args = ["help"]
    extra_args = get_extra_args(args)
    # Verbosity is always included - server extracts it as context
    assert extra_args == {"verbosity": 1}


def test_extra_args_deploy_without_app_name():
    """Deploy without app name should not generate archive."""
    args = ["deploy"]
    extra_args = get_extra_args(args)
    # No repository since no app name - let server return usage error
    assert "repository" not in extra_args
    assert "verbosity" in extra_args


def test_extra_args_deploy_with_app_name(tmp_path):
    """Deploy with app name should generate archive."""
    # The conftest's autouse fixture chdirs to tmp_path so tests don't
    # accidentally package the repo. The archive-generation helper
    # refuses an empty directory, so seed it with a token file.
    tmp_path.joinpath("hop3.toml").write_text('[metadata]\nid = "myapp"\n')
    args = ["deploy", "myapp"]
    extra_args = get_extra_args(args)
    assert "repository" in extra_args
    assert "verbosity" in extra_args
    assert "streaming" in extra_args
