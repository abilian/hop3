# Copyright (c) 2025, Abilian SAS
"""
Misc tests for the RPC client.
"""

from __future__ import annotations

from hop3_cli.main import get_extra_args


def test_extra_args():
    args = ["help"]
    extra_args = get_extra_args(args)
    assert extra_args == {}


def test_extra_args_deploy():
    args = ["deploy"]
    extra_args = get_extra_args(args)
    assert "repository" in extra_args
    assert "verbosity" in extra_args
