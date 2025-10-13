# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Test builder initialization with DeploymentContext and legacy signatures."""

from __future__ import annotations

from pathlib import Path

from hop3.builders.python import PythonBuilder
from hop3.core.protocols import BuildArtifact, DeploymentContext


def test_builder_with_deployment_context(tmp_path: Path):
    """Test that Builder can be initialized with a DeploymentContext object."""
    # Create source directory with requirements.txt so PythonBuilder accepts it
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Initialize builder with context
    builder = PythonBuilder(context)

    # Verify attributes
    assert builder.app_name == "test-app"
    assert builder.app_path == tmp_path
    assert builder.src_path == src_dir
    assert builder.context == context
    assert builder.accept() is True


def test_builder_with_legacy_signature(tmp_path: Path):
    """Test that Builder can be initialized with legacy string signature."""
    # Create source directory
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Initialize builder with legacy signature
    builder = PythonBuilder("legacy-app", tmp_path)

    # Verify attributes
    assert builder.app_name == "legacy-app"
    assert builder.app_path == tmp_path
    assert builder.src_path == src_dir
    assert builder.context is None
    assert builder.accept() is True


def test_builder_with_pyproject_toml(tmp_path: Path):
    """Test that Builder accepts pyproject.toml files."""
    # Create source directory with pyproject.toml
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\n'
    )

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Initialize builder with context
    builder = PythonBuilder(context)

    # Verify it accepts pyproject.toml
    assert builder.accept() is True


def test_builder_rejects_non_python_project(tmp_path: Path):
    """Test that PythonBuilder rejects projects without Python markers."""
    # Create source directory without Python files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "package.json").write_text('{"name": "test"}\n')

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Initialize builder with context
    builder = PythonBuilder(context)

    # Verify it rejects non-Python projects
    assert builder.accept() is False


def test_builder_returns_build_artifact(tmp_path: Path, monkeypatch):
    """Test that build() returns a BuildArtifact."""
    # Create source directory with requirements.txt
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Initialize builder with context
    builder = PythonBuilder(context)

    # Change to source directory
    monkeypatch.chdir(src_dir)

    # Build the app
    artifact = builder.build()

    # Verify build() returns a BuildArtifact
    assert isinstance(artifact, BuildArtifact)
    assert artifact.kind == "virtualenv"
    assert artifact.location == str(tmp_path / "venv")
    assert artifact.metadata["app_name"] == "test-app"
    assert "python_path" in artifact.metadata
