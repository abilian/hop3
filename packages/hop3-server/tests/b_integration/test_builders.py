# Copyright (c) 2024-2025, Abilian SAS

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hop3.core.protocols import BuildArtifact, DeploymentContext
from hop3.toolchains import (
    GoToolchain,
    NodeToolchain,
    PythonToolchain,
    RubyToolchain,
)

# Directory containing test apps
TEST_APPS_DIR = Path("apps/test-apps")


def _detect_toolchain(app_path: Path) -> type | None:
    """Detect which toolchain to use based on files in the app directory.

    Returns None if no supported toolchain is detected.
    """
    # Check for Python indicators
    if (app_path / "requirements.txt").exists() or (
        app_path / "pyproject.toml"
    ).exists():
        return PythonToolchain

    # Check for Node.js indicators
    if (app_path / "package.json").exists():
        return NodeToolchain

    # Check for Go indicators
    if (app_path / "go.mod").exists():
        return GoToolchain

    # Check for Ruby indicators
    if (app_path / "Gemfile").exists():
        return RubyToolchain

    return None


def _discover_test_apps() -> list[tuple[str, type]]:
    """Discover test apps and their toolchains dynamically.

    Returns list of (app_name, toolchain_class) tuples.
    """
    if not TEST_APPS_DIR.exists():
        return []

    apps = []
    for app_dir in sorted(TEST_APPS_DIR.iterdir()):
        if not app_dir.is_dir():
            continue
        # Skip hidden directories and special directories
        if app_dir.name.startswith(".") or app_dir.name.startswith("_"):
            continue

        toolchain = _detect_toolchain(app_dir)
        if toolchain:
            apps.append((app_dir.name, toolchain))

    return apps


# Dynamically discover apps
APPS = _discover_test_apps()


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

    # Stub the network pip-install step — this test verifies build() returns a
    # well-formed BuildArtifact and creates a real venv, not that flask installs
    # over the network (real installs are covered by the c_e2e deploy tests).
    orig_shell = toolchain.shell

    def shell_no_pip(cmd, *args, **kwargs):
        return None if "pip install" in cmd else orig_shell(cmd, *args, **kwargs)

    monkeypatch.setattr(toolchain, "shell", shell_no_pip)

    # Build the app
    artifact = toolchain.build()

    # Verify build() returns a BuildArtifact
    assert isinstance(artifact, BuildArtifact)
    assert artifact.kind == "python"
    assert artifact.app_name == "test-app"
    assert artifact.location == str(src_dir)
    assert "python_path" in artifact.metadata
    # Verify runtime config is populated
    assert artifact.runtime is not None
    assert "PYTHONUNBUFFERED" in artifact.runtime.env_vars
