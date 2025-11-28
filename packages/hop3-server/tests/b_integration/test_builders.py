# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hop3.builders import (
    GoToolchain,
    NodeToolchain,
    PythonToolchain,
    RubyToolchain,
)
from hop3.core.protocols import BuildArtifact, DeploymentContext

APPS = [
    # ("000-static", PythonToolchain),
    ("010-flask-pip-wsgi", PythonToolchain),
    ("020-nodejs-express", NodeToolchain),
    ("030-golang-gin", GoToolchain),
    ("040-sinatra", RubyToolchain),
    ("100-flask-gunicorn-pip", PythonToolchain),
    ("110-flask-gunicorn-poetry", PythonToolchain),
    # ("120-flask-pip-alt", PythonToolchain),
    ("130-golang-minimal", GoToolchain),
]


@pytest.mark.parametrize(("app_name", "toolchain_cls"), APPS)
def test_builders(tmp_path, app_name, toolchain_cls):
    # Temp
    Path("/tmp/hop3/envs").mkdir(exist_ok=True, parents=True)

    # Copy app to src directory
    app_path = tmp_path / app_name
    app_path.mkdir()
    shutil.copytree(f"apps/test-apps/{app_name}", app_path / "src")

    toolchain = toolchain_cls(app_name, app_path)
    assert toolchain.accept()

    toolchain.build()
    # Nothing to assert, toolchain would raise an exception if something went wrong


def test_builder_returns_build_artifact(tmp_path: Path, monkeypatch):
    """Test that build() returns a BuildArtifact."""
    # Create source directory with requirements.txt
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "requirements.txt").write_text("flask==2.0.0\n")

    # Create DeploymentContext
    context = DeploymentContext(app_name="test-app", source_path=src_dir, app_config={})

    # Initialize toolchain with context
    toolchain = PythonToolchain(context)

    # Change to source directory
    monkeypatch.chdir(src_dir)

    # Build the app
    artifact = toolchain.build()

    # Verify build() returns a BuildArtifact
    assert isinstance(artifact, BuildArtifact)
    assert artifact.kind == "virtualenv"
    assert artifact.location == str(tmp_path / "venv")
    assert artifact.metadata["app_name"] == "test-app"
    assert "python_path" in artifact.metadata
