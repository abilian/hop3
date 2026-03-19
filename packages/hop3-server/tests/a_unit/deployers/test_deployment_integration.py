# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Test deployment integration."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

from hop3.core.plugins import get_deployer
from hop3.core.protocols import BuildArtifact, DeploymentContext
from hop3.orm import App

if TYPE_CHECKING:
    from pathlib import Path


def test_uwsgi_deployer_selected_for_virtualenv(tmp_path: Path):
    """Test that UWSGIDeployer is selected for virtualenv artifacts."""
    # Create a mock app
    app = Mock(spec=App)
    app.name = "test-app"
    app.src_path = tmp_path / "src"
    app.src_path.mkdir(parents=True)

    # Create deployment context with app
    context = DeploymentContext(
        app_name="test-app",
        source_path=app.src_path,
        app_config={},
        app=app,
    )

    # Create a virtualenv artifact
    artifact = BuildArtifact(
        kind="virtualenv",
        builder="local",
        app_name="test-app",
        built_at="2025-02-23T10:00:00Z",
        build_id="abc123",
        location=str(tmp_path / "venv"),
        metadata={"python_path": str(tmp_path / "venv" / "bin" / "python")},
    )

    # Get deployment strategy
    deployer = get_deployer(context, artifact)

    # Verify it's the UWSGIDeployer
    assert deployer.name == "uwsgi"
    assert deployer.accept() is True


def test_uwsgi_deployer_has_app_access(tmp_path: Path):
    """Test that UWSGIDeployer can access the app from context."""
    # Create a real App instance
    app = App(name="test-app")

    # Create source directory first
    source_path = tmp_path / "src"
    source_path.mkdir(parents=True)

    # Create deployment context with app
    context = DeploymentContext(
        app_name="test-app",
        source_path=source_path,
        app_config={},
        app=app,
    )

    # Create artifact
    artifact = BuildArtifact(
        kind="virtualenv",
        builder="local",
        app_name="test-app",
        built_at="2025-02-23T10:00:00Z",
        build_id="abc123",
        location=str(tmp_path / "venv"),
        metadata={},
    )

    # Get deployment strategy
    deployer = get_deployer(context, artifact)

    # Verify the deployer can access the app
    assert deployer.app == app
    assert deployer.app.name == "test-app"


def test_deployment_strategy_priority(tmp_path: Path):
    """Test that UWSGIDeployer is selected for various artifact types."""
    app = Mock(spec=App)
    app.name = "test-app"

    # Create source directory first
    source_path = tmp_path / "src"
    source_path.mkdir(parents=True)

    context = DeploymentContext(
        app_name="test-app",
        source_path=source_path,
        app_config={},
        app=app,
    )

    # Test with virtualenv artifact
    artifact = BuildArtifact(
        kind="virtualenv",
        builder="local",
        app_name="test-app",
        built_at="2025-02-23T10:00:00Z",
        build_id="abc123",
        location="/tmp/venv",
        metadata={},
    )
    deployer = get_deployer(context, artifact)
    assert deployer.name == "uwsgi", "UWSGIDeployer should be selected for virtualenv"

    # Test with node artifact
    artifact = BuildArtifact(
        kind="node",
        builder="local",
        app_name="test-app",
        built_at="2025-02-23T10:00:00Z",
        build_id="abc123",
        location="/tmp/node",
        metadata={},
    )
    deployer = get_deployer(context, artifact)
    assert deployer.name == "uwsgi", "UWSGIDeployer should be selected for node"

    # Test with buildpack artifact
    artifact = BuildArtifact(
        kind="buildpack",
        builder="local",
        app_name="test-app",
        built_at="2025-02-23T10:00:00Z",
        build_id="abc123",
        location="/tmp/bp",
        metadata={},
    )
    deployer = get_deployer(context, artifact)
    assert deployer.name == "uwsgi", "UWSGIDeployer should be selected for buildpack"
