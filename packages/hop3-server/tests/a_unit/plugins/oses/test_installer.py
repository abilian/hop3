# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for OS setup strategies (plugin system)."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from hop3.plugins.oses.base import BaseOSStrategy


def test_put_file() -> None:
    """Test that put_file() can write content to a file."""
    strategy = BaseOSStrategy()
    dummy = StringIO("dummy")
    strategy.put_file("test", dummy, "/tmp/test_installer.py")

    assert Path("/tmp/test_installer.py").exists()

    Path("/tmp/test_installer.py").unlink()


def test_ensure_link() -> None:
    """Test that ensure_link() can create a symbolic link."""
    strategy = BaseOSStrategy()
    Path("/tmp/dummy").touch()
    strategy.ensure_link("test", "/tmp/dummy2", "/tmp/dummy")

    assert Path("/tmp/dummy2").exists()
    assert Path("/tmp/dummy2").is_symlink()

    Path("/tmp/dummy").unlink()
    Path("/tmp/dummy2").unlink()
