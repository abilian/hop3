# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Test builder initialization with DeploymentContext and legacy signatures."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.builders.python import PythonToolchain
from hop3.core.protocols import DeploymentContext

if TYPE_CHECKING:
    from pathlib import Path


def test_toolchain_with_deployment_context(tmp_path: Path):
    """Test that LanguageToolchain can be initialized with a DeploymentContext object."""
    # Create source directory with requirements.txt so PythonToolchain accepts it
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Initialize toolchain with context
    toolchain = PythonToolchain(context)

    # Verify attributes
    assert toolchain.app_name == "test-app"
    assert toolchain.app_path == tmp_path
    assert toolchain.src_path == src_dir
    assert toolchain.context == context
    assert toolchain.accept() is True


def test_toolchain_with_legacy_signature(tmp_path: Path):
    """Test that LanguageToolchain can be initialized with legacy string signature."""
    # Create source directory
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Initialize toolchain with legacy signature
    toolchain = PythonToolchain("legacy-app", tmp_path)

    # Verify attributes
    assert toolchain.app_name == "legacy-app"
    assert toolchain.app_path == tmp_path
    assert toolchain.src_path == src_dir
    assert toolchain.context is None
    assert toolchain.accept() is True


def test_toolchain_with_pyproject_toml(tmp_path: Path):
    """Test that LanguageToolchain accepts pyproject.toml files."""
    # Create source directory with pyproject.toml
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\n'
    )

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Initialize toolchain with context
    toolchain = PythonToolchain(context)

    # Verify it accepts pyproject.toml
    assert toolchain.accept() is True


def test_toolchain_rejects_non_python_project(tmp_path: Path):
    """Test that PythonToolchain rejects projects without Python markers."""
    # Create source directory without Python files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "package.json").write_text('{"name": "test"}\n')

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Initialize toolchain with context
    toolchain = PythonToolchain(context)

    # Verify it rejects non-Python projects
    assert toolchain.accept() is False
