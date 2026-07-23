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


def test_extra_args_deploy_packs_cwd_by_default(tmp_path):
    """
    Deploy packs the current directory by default. The app is the `--app`
    flag (ADR 036 D5), resolved/injected at a higher layer — never a positional
    here, so the only positional deploy takes is an optional source directory.
    """
    # The conftest's autouse fixture chdirs to tmp_path; the archive helper
    # refuses an empty directory, so seed it with a token file.
    tmp_path.joinpath("hop3.toml").write_text('[metadata]\nid = "myapp"\n')
    extra_args = get_extra_args(["deploy"])
    assert "repository" in extra_args
    assert extra_args["streaming"] is True


def test_extra_args_deploy_strips_app_flag(tmp_path):
    """
    `--app NAME` is stripped (not mistaken for the source directory); the
    current directory is packed.
    """
    tmp_path.joinpath("hop3.toml").write_text('[metadata]\nid = "myapp"\n')
    extra_args = get_extra_args(["deploy", "--app", "myapp"])
    assert "repository" in extra_args
    assert "verbosity" in extra_args
    assert "streaming" in extra_args
