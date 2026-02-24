# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Tests for build artifact model."""

from __future__ import annotations

import json
from pathlib import Path

from hop3.core.artifacts import BuildArtifact, RuntimeConfig


class TestRuntimeConfig:
    """Tests for RuntimeConfig dataclass."""

    def test_defaults(self):
        """RuntimeConfig should have sensible defaults."""
        config = RuntimeConfig()
        assert config.env_vars == {}
        assert config.path_prepend == []
        assert config.working_dir == ""
        assert config.workers == {}

    def test_with_values(self):
        """RuntimeConfig should accept values."""
        config = RuntimeConfig(
            env_vars={"PYTHONPATH": "/app/src"},
            path_prepend=["/app/venv/bin"],
            working_dir="/app",
            workers={"web": "gunicorn app:app"},
        )
        assert config.env_vars["PYTHONPATH"] == "/app/src"
        assert "/app/venv/bin" in config.path_prepend
        assert config.working_dir == "/app"
        assert config.workers["web"] == "gunicorn app:app"


class TestBuildArtifact:
    """Tests for BuildArtifact dataclass."""

    def test_minimal_artifact(self):
        """BuildArtifact should work with minimal required fields."""
        artifact = BuildArtifact(kind="python")
        assert artifact.kind == "python"
        assert artifact.builder == "local"  # default
        assert artifact.location == ""  # default
        assert artifact.app_name == ""  # default
        assert artifact.runtime is not None  # default RuntimeConfig

    def test_complete_artifact(self):
        """BuildArtifact should store all fields correctly."""
        runtime = RuntimeConfig(
            env_vars={"PYTHONPATH": "/app/src"},
            path_prepend=["/app/venv/bin"],
            working_dir="/app/src",
            workers={"web": "gunicorn app:app"},
        )
        artifact = BuildArtifact(
            kind="python",
            builder="local",
            app_name="myapp",
            built_at="2025-02-23T10:00:00Z",
            build_id="abc123",
            location="/app/venv",
            runtime=runtime,
            metadata={"python_version": "3.12"},
        )
        assert artifact.kind == "python"
        assert artifact.builder == "local"
        assert artifact.app_name == "myapp"
        assert artifact.built_at == "2025-02-23T10:00:00Z"
        assert artifact.build_id == "abc123"
        assert artifact.location == "/app/venv"
        assert artifact.runtime.env_vars["PYTHONPATH"] == "/app/src"
        assert artifact.metadata["python_version"] == "3.12"


class TestBuildArtifactSerialization:
    """Tests for BuildArtifact serialization."""

    def test_to_dict(self):
        """BuildArtifact should serialize to dict correctly."""
        artifact = BuildArtifact(
            kind="python",
            builder="local",
            app_name="myapp",
            built_at="2025-02-23T10:00:00Z",
            build_id="abc123",
            location="/app/venv",
            runtime=RuntimeConfig(
                env_vars={"KEY": "value"},
                path_prepend=["/bin"],
            ),
        )
        data = artifact.to_dict()
        assert data["kind"] == "python"
        assert data["builder"] == "local"
        assert data["app_name"] == "myapp"
        assert data["runtime"]["env_vars"]["KEY"] == "value"
        assert "/bin" in data["runtime"]["path_prepend"]

    def test_to_json(self):
        """BuildArtifact should serialize to JSON correctly."""
        artifact = BuildArtifact(kind="node", app_name="nodeapp")
        json_str = artifact.to_json()
        data = json.loads(json_str)
        assert data["kind"] == "node"
        assert data["app_name"] == "nodeapp"

    def test_from_dict(self):
        """BuildArtifact should deserialize from dict correctly."""
        data = {
            "kind": "ruby",
            "builder": "local",
            "app_name": "rubyapp",
            "built_at": "2025-02-23T10:00:00Z",
            "build_id": "xyz789",
            "location": "/app/gems",
            "runtime": {
                "env_vars": {"GEM_HOME": "/app/gems"},
                "path_prepend": ["/app/gems/bin"],
                "working_dir": "/app",
                "workers": {"web": "puma"},
            },
            "metadata": {},
        }
        artifact = BuildArtifact.from_dict(data)
        assert artifact.kind == "ruby"
        assert artifact.app_name == "rubyapp"
        assert artifact.runtime.env_vars["GEM_HOME"] == "/app/gems"
        assert artifact.runtime.workers["web"] == "puma"

    def test_from_json(self):
        """BuildArtifact should deserialize from JSON correctly."""
        json_str = '{"kind": "go", "builder": "local", "app_name": "goapp", "built_at": "", "build_id": "", "location": "", "runtime": {"env_vars": {}, "path_prepend": [], "working_dir": "", "workers": {}}, "metadata": {}}'
        artifact = BuildArtifact.from_json(json_str)
        assert artifact.kind == "go"
        assert artifact.app_name == "goapp"

    def test_roundtrip(self):
        """BuildArtifact should survive serialization round-trip."""
        original = BuildArtifact(
            kind="python",
            builder="local",
            app_name="myapp",
            built_at="2025-02-23T10:00:00Z",
            build_id="abc123",
            location="/home/hop3/apps/myapp/venv",
            runtime=RuntimeConfig(
                env_vars={"PYTHONPATH": "/home/hop3/apps/myapp/src/src"},
                path_prepend=["/home/hop3/apps/myapp/venv/bin"],
                working_dir="/home/hop3/apps/myapp/src",
                workers={"web": "gunicorn app:app"},
            ),
            metadata={"python_version": "3.12"},
        )
        json_str = original.to_json()
        loaded = BuildArtifact.from_json(json_str)

        assert loaded.kind == original.kind
        assert loaded.builder == original.builder
        assert loaded.app_name == original.app_name
        assert loaded.built_at == original.built_at
        assert loaded.build_id == original.build_id
        assert loaded.location == original.location
        assert loaded.runtime.env_vars == original.runtime.env_vars
        assert loaded.runtime.path_prepend == original.runtime.path_prepend
        assert loaded.runtime.working_dir == original.runtime.working_dir
        assert loaded.runtime.workers == original.runtime.workers
        assert loaded.metadata == original.metadata


class TestBuildArtifactFileIO:
    """Tests for BuildArtifact file operations."""

    def test_save_and_load(self, tmp_path: Path):
        """BuildArtifact should save to and load from file."""
        artifact = BuildArtifact(
            kind="python",
            builder="local",
            app_name="myapp",
            built_at="2025-02-23T10:00:00Z",
            build_id="abc123",
            location="/app",
            runtime=RuntimeConfig(
                env_vars={"KEY": "value"},
            ),
        )
        artifact_path = tmp_path / "BUILD_ARTIFACT.json"
        artifact.save(artifact_path)

        assert artifact_path.exists()

        loaded = BuildArtifact.load(artifact_path)
        assert loaded is not None
        assert loaded.kind == "python"
        assert loaded.app_name == "myapp"
        assert loaded.runtime.env_vars["KEY"] == "value"

    def test_load_nonexistent_file(self, tmp_path: Path):
        """BuildArtifact.load should return None for missing file."""
        artifact_path = tmp_path / "nonexistent.json"
        artifact = BuildArtifact.load(artifact_path)
        assert artifact is None

    def test_load_invalid_json(self, tmp_path: Path):
        """BuildArtifact.load should return None for invalid JSON."""
        artifact_path = tmp_path / "invalid.json"
        artifact_path.write_text("not valid json {{{")
        artifact = BuildArtifact.load(artifact_path)
        assert artifact is None

    def test_load_incomplete_data(self, tmp_path: Path):
        """BuildArtifact.load should return None for incomplete data."""
        artifact_path = tmp_path / "incomplete.json"
        # Missing required 'kind' field
        artifact_path.write_text('{"builder": "local"}')
        artifact = BuildArtifact.load(artifact_path)
        assert artifact is None


class TestBuildArtifactBackwardsCompatibility:
    """Tests for backwards compatibility with existing code."""

    def test_minimal_fields_for_existing_tests(self):
        """BuildArtifact should work with minimal fields for backwards compat."""
        # This is how existing tests create artifacts
        artifact = BuildArtifact(
            kind="virtualenv",
            builder="local",
            app_name="test-app",
            built_at="2025-02-23T10:00:00Z",
            build_id="abc123",
            location="/tmp/venv",
            metadata={},
        )
        assert artifact.kind == "virtualenv"
        assert artifact.builder == "local"
        assert artifact.app_name == "test-app"
        assert artifact.runtime is not None  # Has default RuntimeConfig
