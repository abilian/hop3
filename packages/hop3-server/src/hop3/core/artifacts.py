# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Build artifact model - the contract between build and run phases.

This module defines the BuildArtifact and RuntimeConfig dataclasses that
represent the output of the build phase and contain everything needed
for the run phase.

The key principle is that the run phase should NOT need to detect or infer
anything about the application - all runtime configuration is computed
during build and stored in the artifact.

Example usage:
    # During build (in a toolchain)
    runtime = RuntimeConfig(
        env_vars={"PYTHONPATH": "/app/src"},
        path_prepend=["/app/venv/bin"],
        working_dir="/app",
        workers={"web": "gunicorn app:app"},
    )
    artifact = BuildArtifact(
        kind="python",
        builder="local",
        app_name="myapp",
        built_at="2025-02-23T10:00:00Z",
        build_id="abc123",
        location="/app",
        runtime=runtime,
    )
    artifact.save(Path("/app/BUILD_ARTIFACT.json"))

    # During run (in spawn.py)
    artifact = BuildArtifact.load(Path("/app/BUILD_ARTIFACT.json"))
    if artifact:
        for key, value in artifact.runtime.env_vars.items():
            env[key] = value
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RuntimeConfig:
    """Runtime configuration computed during build.

    This is everything the run phase needs to know to execute the app.
    The run phase should NOT need to detect or infer anything.
    """

    # Environment variables (absolute paths, fully resolved)
    env_vars: dict[str, str] = field(default_factory=dict)

    # Paths to prepend to PATH (in order, absolute)
    path_prepend: list[str] = field(default_factory=list)

    # Working directory for processes (absolute path)
    working_dir: str = ""

    # Workers from Procfile, commands fully resolved
    # e.g., {"web": "gunicorn app:app", "worker": "celery -A tasks worker"}
    workers: dict[str, str] = field(default_factory=dict)


@dataclass
class BuildArtifact:
    """Self-describing build output - like an OCI image manifest.

    Produced by the build phase, consumed by the run phase.
    Contains everything needed to run the app.

    Note: builder, app_name, built_at, build_id have defaults for backwards
    compatibility during the migration period. New code should always provide
    these values explicitly.
    """

    # What produced this artifact
    kind: str  # Language/type: "python", "node", "nix", "docker", "static"

    # Where outputs live
    location: str = ""  # Root path, /nix/store path, or image reference

    # Additional metadata (toolchain-specific, for debugging/auditing)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Builder used: "local", "nix", "docker" (default for backwards compat)
    builder: str = "local"

    # Build metadata (defaults for backwards compatibility)
    app_name: str = ""
    built_at: str = ""  # ISO 8601 timestamp
    build_id: str = ""  # Unique ID for this build (UUID or git SHA)

    # Runtime configuration
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: Path) -> None:
        """Save artifact to JSON file."""
        path.write_text(self.to_json())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BuildArtifact:
        """Create from dictionary."""
        # Handle nested RuntimeConfig
        runtime_data = data.pop("runtime", {})
        runtime = RuntimeConfig(**runtime_data)
        return cls(runtime=runtime, **data)

    @classmethod
    def from_json(cls, text: str) -> BuildArtifact:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: Path) -> BuildArtifact | None:
        """Load artifact from JSON file.

        Returns None if file doesn't exist or is invalid.
        """
        if not path.exists():
            return None
        try:
            return cls.from_json(path.read_text())
        except (json.JSONDecodeError, TypeError, KeyError):
            return None
