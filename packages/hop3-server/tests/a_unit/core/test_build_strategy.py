# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Test build strategy plugin integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from hop3.core.plugins import get_build_strategy
from hop3.core.protocols import DeploymentContext


def test_get_build_strategy_with_python_project(tmp_path: Path):
    """Test that get_build_strategy returns a PythonBuilder for Python projects."""
    # Create source directory with requirements.txt
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Get build strategy
    builder = get_build_strategy(context)

    # Verify it's a Python builder
    assert builder.name == "Python"
    assert builder.app_name == "test-app"
    assert builder.app_path == tmp_path
    assert builder.src_path == src_dir
    assert builder.context == context


def test_get_build_strategy_with_node_project(tmp_path: Path):
    """Test that get_build_strategy returns a NodeBuilder for Node projects."""
    # Create source directory with package.json
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "package.json").write_text('{"name": "test", "version": "1.0.0"}\n')

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Get build strategy
    builder = get_build_strategy(context)

    # Verify it's a Node builder
    assert builder.name == "Node"
    assert builder.app_name == "test-app"
    assert builder.app_path == tmp_path
    assert builder.context == context


def test_get_build_strategy_no_suitable_builder(tmp_path: Path):
    """Test that get_build_strategy raises error when no builder accepts the project."""
    # Create source directory without any recognized project files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "README.md").write_text("# Test Project\n")

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Verify it raises an error when no builder accepts the project
    with pytest.raises(RuntimeError, match="Could not find a suitable build strategy"):
        get_build_strategy(context)
