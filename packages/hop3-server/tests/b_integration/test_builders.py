# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hop3.builders import (
    GoBuilder,
    NodeBuilder,
    PythonBuilder,
    RubyBuilder,
)
from hop3.core.protocols import BuildArtifact, DeploymentContext

APPS = [
    # ("000-static", PythonBuilder),
    ("010-flask-pip-wsgi", PythonBuilder),
    ("020-nodejs-express", NodeBuilder),
    ("030-golang-gin", GoBuilder),
    ("040-sinatra", RubyBuilder),
    ("100-flask-gunicorn-pip", PythonBuilder),
    ("110-flask-gunicorn-poetry", PythonBuilder),
    # ("120-flask-pip-alt", PythonBuilder),
    ("130-golang-minimal", GoBuilder),
]


@pytest.mark.parametrize(("app_name", "builder_cls"), APPS)
def test_builders(tmp_path, app_name, builder_cls):
    # Temp
    Path("/tmp/hop3/envs").mkdir(exist_ok=True, parents=True)

    # Copy app to src directory
    app_path = tmp_path / app_name
    app_path.mkdir()
    shutil.copytree(f"apps/test-apps/{app_name}", app_path / "src")

    builder = builder_cls(app_name, app_path)
    assert builder.accept()

    builder.build()
    # Nothing to assert, builder would raise an exception if something went wrong


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
