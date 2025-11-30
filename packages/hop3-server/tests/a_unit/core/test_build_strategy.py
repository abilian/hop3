# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Test build strategy plugin integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.core.plugins import get_builder
from hop3.core.protocols import DeploymentContext

if TYPE_CHECKING:
    from pathlib import Path


def test_get_builder_with_python_project(tmp_path: Path):
    """Test that get_builder returns LocalBuilder for Python projects."""
    # Create source directory with requirements.txt
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Get builder
    builder = get_builder(context)

    # Verify it's LocalBuilder (which internally uses PythonToolchain)
    assert builder.name == "local"
    assert builder.context == context


def test_get_builder_with_node_project(tmp_path: Path):
    """Test that get_builder returns LocalBuilder for Node projects."""
    # Create source directory with package.json
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "package.json").write_text('{"name": "test", "version": "1.0.0"}\n')

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Get builder
    builder = get_builder(context)

    # Verify it's LocalBuilder (which internally uses NodeToolchain)
    assert builder.name == "local"
    assert builder.context == context


def test_get_builder_no_suitable_builder(tmp_path: Path):
    """Test that get_builder uses DummyBuilder when .dummy-build marker exists."""
    # Create source directory without any recognized project files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "README.md").write_text("# Test Project\n")

    # Create .dummy-build marker file to explicitly request DummyBuilder
    # (DummyBuilder only accepts if this marker exists)
    (src_dir / ".dummy-build").touch()

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # With .dummy-build marker, DummyBuilder should accept
    builder = get_builder(context)
    assert builder.name == "dummy"


def test_get_builder_no_builder_raises_error(tmp_path: Path):
    """Test that get_builder raises RuntimeError when no builder accepts."""
    # Create source directory without any recognized project files
    # and WITHOUT .dummy-build marker
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "README.md").write_text("# Test Project\n")

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Without any recognized files or .dummy-build marker, should raise RuntimeError
    with pytest.raises(RuntimeError, match="Could not find a suitable builder"):
        get_builder(context)
