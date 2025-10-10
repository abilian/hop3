# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Test virtualenv repair functionality."""

from __future__ import annotations

from pathlib import Path

from hop3.builders.python import PythonBuilder


def test_broken_virtualenv_is_recreated(tmp_path: Path, monkeypatch):
    """Test that a broken virtualenv (with broken symlinks) is recreated."""
    # Create app structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Create a fake broken virtualenv with broken symlink
    venv_dir = tmp_path / "venv"
    venv_bin = venv_dir / "bin"
    venv_bin.mkdir(parents=True)

    # Create a broken symlink (pointing to non-existent Python)
    python_link = venv_bin / "python"
    python_link.symlink_to("/nonexistent/path/to/python3.13")

    # Verify the symlink is broken
    assert venv_bin.exists()
    assert not python_link.exists()  # Broken symlink

    # Create builder
    builder = PythonBuilder("test-app", tmp_path)

    # Change to the source directory (required by builder)
    monkeypatch.chdir(src_dir)

    # Call make_virtual_env - should detect and fix broken virtualenv
    builder.make_virtual_env()

    # Verify the virtualenv was recreated with working Python
    assert python_link.exists()
    # Verify it's actually executable and working
    import subprocess

    result = subprocess.run(
        [str(python_link), "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Python" in result.stdout or "Python" in result.stderr


def test_working_virtualenv_is_not_recreated(tmp_path: Path, monkeypatch):
    """Test that a working virtualenv is not recreated unnecessarily."""
    # Create app structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Create builder
    builder = PythonBuilder("test-app", tmp_path)

    # Change to the source directory
    monkeypatch.chdir(src_dir)

    # Create virtualenv first time
    builder.make_virtual_env()

    # Get the creation time
    python_link = tmp_path / "venv" / "bin" / "python"
    stat1 = python_link.stat()

    # Call make_virtual_env again - should NOT recreate
    import time

    time.sleep(0.1)  # Ensure time difference would be detectable
    builder.make_virtual_env()

    # Verify it wasn't recreated (same inode/creation time)
    stat2 = python_link.stat()
    assert stat1.st_ino == stat2.st_ino
