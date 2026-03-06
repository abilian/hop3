# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DockerBuilder."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from hop3.core.protocols import BuildContext
from hop3.lib import Abort
from hop3.plugins.docker.builder import DockerBuilder

if TYPE_CHECKING:
    from pathlib import Path


class TestDockerBuilderAccept:
    """Tests for DockerBuilder.accept() method."""

    def test_accept_with_dockerfile(self, tmp_path: Path):
        """Should accept when Dockerfile exists."""
        # Create Dockerfile
        (tmp_path / "Dockerfile").write_text("FROM python:3.11\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder.accept() is True

    def test_reject_without_dockerfile(self, tmp_path: Path):
        """Should reject when no Dockerfile exists."""
        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder.accept() is False

    def test_reject_with_dockerfile_directory(self, tmp_path: Path):
        """Should reject when Dockerfile is a directory, not a file."""
        (tmp_path / "Dockerfile").mkdir()

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder.accept() is False


class TestDockerBuilderImageTag:
    """Tests for image tag generation."""

    def test_generate_image_tag_simple(self, tmp_path: Path):
        """Should generate correct image tag for simple app name."""
        context = BuildContext(
            app_name="myapp",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder._generate_image_tag() == "hop3/myapp:latest"

    def test_generate_image_tag_with_underscores(self, tmp_path: Path):
        """Should convert underscores to hyphens in image tag."""
        context = BuildContext(
            app_name="my_app_name",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder._generate_image_tag() == "hop3/my-app-name:latest"

    def test_generate_image_tag_lowercase(self, tmp_path: Path):
        """Should convert app name to lowercase."""
        context = BuildContext(
            app_name="MyApp",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder._generate_image_tag() == "hop3/myapp:latest"


class TestDockerBuilderMetadataExtraction:
    """Tests for Dockerfile metadata extraction."""

    def test_extract_single_exposed_port(self, tmp_path: Path):
        """Should extract single EXPOSE port from Dockerfile."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nEXPOSE 8080\nCMD python app.py\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        metadata = builder._extract_metadata()

        assert metadata["app_name"] == "test-app"
        assert metadata["builder"] == "docker"
        assert metadata["exposed_ports"] == [8080]

    def test_extract_multiple_exposed_ports(self, tmp_path: Path):
        """Should extract multiple EXPOSE ports from Dockerfile."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM nginx\nEXPOSE 80 443\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        metadata = builder._extract_metadata()

        assert metadata["exposed_ports"] == [80, 443]

    def test_extract_port_with_protocol(self, tmp_path: Path):
        """Should extract port even with protocol suffix."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM nginx\nEXPOSE 8080/tcp\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        metadata = builder._extract_metadata()

        assert metadata["exposed_ports"] == [8080]

    def test_no_exposed_ports(self, tmp_path: Path):
        """Should handle Dockerfile without EXPOSE."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nCMD python app.py\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        metadata = builder._extract_metadata()

        assert "exposed_ports" not in metadata


class TestDockerBuilderBuild:
    """Tests for DockerBuilder.build() method."""

    def test_build_success(self, tmp_path: Path):
        """Should return BuildArtifact on successful build."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\nEXPOSE 8080\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Successfully built abc123\n",
            )

            artifact = builder.build()

            assert artifact.kind == "docker-image"
            assert artifact.location == "hop3/test-app:latest"
            assert artifact.metadata["app_name"] == "test-app"
            assert artifact.metadata["exposed_ports"] == [8080]

    def test_build_docker_not_found(self, tmp_path: Path):
        """Should raise Abort when Docker is not installed."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            with pytest.raises(Abort, match="Docker command not found"):
                builder.build()

    def test_build_failure(self, tmp_path: Path):
        """Should raise Abort when docker build fails."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM nonexistent:image\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "docker build", stderr="Error: image not found"
            )

            with pytest.raises(Abort, match="Docker build failed"):
                builder.build()

    def test_build_timeout(self, tmp_path: Path):
        """Should raise Abort when build times out."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM python:3.11\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("docker build", 600)

            with pytest.raises(Abort, match="timed out"):
                builder.build()
