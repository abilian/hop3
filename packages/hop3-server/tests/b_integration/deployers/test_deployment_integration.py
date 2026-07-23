# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Integration tests for deployment strategy selection using state-based testing.

This module migrates unit tests to state-based integration tests:
- Tests deployment strategy selection with real database state
- Mocks ONLY external I/O boundaries (plugin system, file I/O)
- Verifies actual deployment strategy selection logic, not mock calls
- Uses ARRANGE/ACT/ASSERT pattern with clear documentation
- Each test validates strategy selection for different artifact types

Key Design:
- Uses real App instances from database, not mocks
- Validates strategy priority and acceptance
- Tests strategy access to app context and artifact metadata
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from hop3.core.plugins import get_deployer
from hop3.core.protocols import BuildArtifact, DeploymentContext
from hop3.orm import App

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.integration
class TestDeploymentStrategySelection:
    """Integration tests for deployment strategy selection logic."""

    def test_uwsgi_deployer_selected_for_virtualenv(self, tmp_path: Path):
        """
        Test that UWSGIDeployer is selected for virtualenv artifacts.

        ARRANGE:
            - Create source directory
            - Create real App instance
            - Create DeploymentContext with app

        ACT:
            - Create virtualenv BuildArtifact
            - Call get_deployer()

        ASSERT:
            - Verify selected deployer has name 'uwsgi'
            - Verify deployer accepts the artifact (accept() returns True)
        """
        source_path = tmp_path / "src"
        source_path.mkdir(parents=True)

        app = App(name="test-app")

        context = DeploymentContext(
            app_name="test-app",
            source_path=source_path,
            app_config={},
            app=app,
        )

        artifact = BuildArtifact(
            kind="virtualenv",
            location=str(tmp_path / "venv"),
            metadata={"python_path": str(tmp_path / "venv" / "bin" / "python")},
        )
        deployer = get_deployer(context, artifact)

        assert deployer.name == "uwsgi"
        assert deployer.accept() is True

    def test_uwsgi_deployer_has_app_access(self, tmp_path: Path):
        """
        Test that UWSGIDeployer can access the app from context.

        ARRANGE:
            - Create real App instance
            - Create source directory
            - Create DeploymentContext with app

        ACT:
            - Create virtualenv BuildArtifact
            - Call get_deployer()
            - Access deployer.app property

        ASSERT:
            - Verify deployer.app is accessible
            - Verify app.name matches
        """
        app = App(name="test-app")
        source_path = tmp_path / "src"
        source_path.mkdir(parents=True)

        context = DeploymentContext(
            app_name="test-app",
            source_path=source_path,
            app_config={},
            app=app,
        )

        artifact = BuildArtifact(
            kind="virtualenv",
            location=str(tmp_path / "venv"),
            metadata={},
        )

        deployer = get_deployer(context, artifact)

        assert cast("Any", deployer).app == app
        assert cast("Any", deployer).app.name == "test-app"

    def test_deployment_strategy_priority_for_multiple_artifacts(self, tmp_path: Path):
        """
        Test that UWSGIDeployer is selected for various artifact types.

        ARRANGE:
            - Create real App instance
            - Create source directory
            - Create DeploymentContext with app

        ACT:
            - Test strategy selection with virtualenv artifact
            - Test strategy selection with node artifact
            - Test strategy selection with buildpack artifact

        ASSERT:
            - Verify UWSGIDeployer is selected for all artifact types
            - Verify consistency across different artifact kinds
        """
        app = App(name="test-app")
        source_path = tmp_path / "src"
        source_path.mkdir(parents=True)

        context = DeploymentContext(
            app_name="test-app",
            source_path=source_path,
            app_config={},
            app=app,
        )

        # ACT & ASSERT: virtualenv artifact
        artifact = BuildArtifact(kind="virtualenv", location="/tmp/venv", metadata={})
        deployer = get_deployer(context, artifact)
        assert deployer.name == "uwsgi", (
            "UWSGIDeployer should be selected for virtualenv"
        )

        # ACT & ASSERT: node artifact
        artifact = BuildArtifact(kind="node", location="/tmp/node", metadata={})
        deployer = get_deployer(context, artifact)
        assert deployer.name == "uwsgi", "UWSGIDeployer should be selected for node"

        # ACT & ASSERT: buildpack artifact
        artifact = BuildArtifact(kind="buildpack", location="/tmp/bp", metadata={})
        deployer = get_deployer(context, artifact)
        assert deployer.name == "uwsgi", (
            "UWSGIDeployer should be selected for buildpack"
        )

    def test_deployment_strategy_context_information(self, tmp_path: Path):
        """
        Test that deployment strategy receives complete context information.

        ARRANGE:
            - Create real App instance
            - Create source directory with specific path
            - Create DeploymentContext with app config

        ACT:
            - Create BuildArtifact with metadata
            - Call get_deployer()
            - Access context from deployer

        ASSERT:
            - Verify context.app_name matches
            - Verify context.source_path is correct
            - Verify app object is accessible
        """
        app = App(name="myapp")
        source_path = tmp_path / "src"
        source_path.mkdir(parents=True)

        app_config = {"worker_count": 4, "timeout": 120}

        context = DeploymentContext(
            app_name="myapp",
            source_path=source_path,
            app_config=app_config,
            app=app,
        )

        artifact = BuildArtifact(
            kind="virtualenv",
            location=str(tmp_path / "venv"),
            metadata={"python_path": "/path/to/python"},
        )
        deployer = get_deployer(context, artifact)

        assert deployer.context.app_name == "myapp"
        assert deployer.context.source_path == source_path
        assert deployer.context.app == app
        assert deployer.context.app_config == app_config

    def test_deployment_strategy_artifact_information(self, tmp_path: Path):
        """
        Test that deployment strategy receives complete artifact information.

        ARRANGE:
            - Create real App instance
            - Create source directory
            - Create BuildArtifact with metadata

        ACT:
            - Call get_deployer()
            - Access artifact from deployer

        ASSERT:
            - Verify artifact.kind is preserved
            - Verify artifact.location is correct
            - Verify artifact.metadata is accessible
        """
        app = App(name="test-app")
        source_path = tmp_path / "src"
        source_path.mkdir(parents=True)

        context = DeploymentContext(
            app_name="test-app",
            source_path=source_path,
            app_config={},
            app=app,
        )

        venv_path = tmp_path / "venv"
        artifact = BuildArtifact(
            kind="virtualenv",
            location=str(venv_path),
            metadata={
                "python_path": f"{venv_path}/bin/python",
                "version": "3.11.0",
            },
        )

        deployer = get_deployer(context, artifact)

        assert deployer.artifact.kind == "virtualenv"
        assert deployer.artifact.location == str(venv_path)
        assert deployer.artifact.metadata["python_path"] == f"{venv_path}/bin/python"
        assert deployer.artifact.metadata["version"] == "3.11.0"
