# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Parser for hop3.toml configuration files.

This module implements parsing for the hop3.toml configuration format as defined
in ADR-001 and ADR-002. It supports the "Convention over Configuration" principle
by making hop3.toml optional and providing sensible defaults.

Validation is performed using Pydantic models defined in schema.py. Unknown
fields are rejected to catch typos early.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib  # Python 3.11+

from hop3.lib import log


@dataclass
class Hop3Config:
    """Represents a parsed hop3.toml configuration file.

    This class provides access to all sections of the hop3.toml file,
    with a focus on the [run] and [build] sections that overlap with
    Procfile functionality.
    """

    # Raw parsed TOML data
    _data: dict[str, Any] = field(default_factory=dict)

    # Parsed path
    config_path: Path | None = None

    @classmethod
    def from_file(cls, filename: str | Path, *, validate: bool = True) -> Hop3Config:
        """Load and parse a hop3.toml file.

        Args:
            filename: Path to the hop3.toml file
            validate: If True, validate against schema (default: True)

        Returns:
            Hop3Config instance with parsed data

        Raises:
            FileNotFoundError: If the file doesn't exist
            TOMLDecodeError: If the file is not valid TOML
            Hop3TomlValidationError: If validation fails
        """
        path = Path(filename)
        if not path.exists():
            msg = f"File not found: {filename}"
            raise FileNotFoundError(msg)

        with path.open("rb") as f:
            data = tomllib.load(f)

        # Validate against schema unless disabled
        # Can be disabled via environment variable for backwards compatibility
        should_validate = validate and not os.environ.get("HOP3_SKIP_CONFIG_VALIDATION")
        if should_validate:
            cls._validate_config(data, path)

        return cls(_data=data, config_path=path)

    @classmethod
    def _validate_config(cls, data: dict[str, Any], path: Path) -> None:
        """Validate configuration data against schema.

        Args:
            data: Parsed TOML data
            path: Path to the config file (for error messages)

        Raises:
            Hop3TomlValidationError: If validation fails
        """
        from hop3.project.schema import (  # noqa: PLC0415
            Hop3TomlValidationError,
            validate_hop3_toml,
        )

        try:
            validate_hop3_toml(data)
            log(f"hop3.toml validated successfully: {path}", level=2, fg="green")
        except Hop3TomlValidationError as e:
            # Log the error before re-raising
            log(f"hop3.toml validation failed: {path}", level=0, fg="red")
            for line in e.message.split("\n"):
                log(f"  {line}", level=0, fg="red")
            raise

    @classmethod
    def from_str(cls, content: str, *, validate: bool = True) -> Hop3Config:
        """Parse hop3.toml content from a string.

        Args:
            content: TOML content as string
            validate: If True, validate against schema (default: True)

        Returns:
            Hop3Config instance with parsed data

        Raises:
            Hop3TomlValidationError: If validation fails
        """
        data = tomllib.loads(content)

        # Validate against schema unless disabled
        should_validate = validate and not os.environ.get("HOP3_SKIP_CONFIG_VALIDATION")
        if should_validate:
            cls._validate_config(data, Path("<string>"))

        return cls(_data=data)

    # =========================================================================
    # [metadata] section
    # =========================================================================

    @property
    def metadata(self) -> dict[str, Any]:
        """Get the [metadata] section."""
        return self._data.get("metadata", {})

    @property
    def app_id(self) -> str | None:
        """Get metadata.id (unique identifier)."""
        return self.metadata.get("id")

    @property
    def version(self) -> str | None:
        """Get metadata.version."""
        return self.metadata.get("version")

    @property
    def title(self) -> str | None:
        """Get metadata.title."""
        return self.metadata.get("title")

    # =========================================================================
    # [build] section
    # =========================================================================

    @property
    def build(self) -> dict[str, Any]:
        """Get the [build] section."""
        return self._data.get("build", {})

    @property
    def build_commands(self) -> list[str]:
        """Get build.build commands (list of shell commands for building).

        Returns:
            List of build commands, empty list if not specified
        """
        build_cmds = self.build.get("build", [])
        # Normalize to list
        if isinstance(build_cmds, str):
            return [build_cmds]
        return build_cmds if isinstance(build_cmds, list) else []

    @property
    def before_build_commands(self) -> list[str]:
        """Get build.before-build commands.

        Returns:
            List of commands to run before build
        """
        cmds = self.build.get("before-build", [])
        if isinstance(cmds, str):
            return [cmds]
        return cmds if isinstance(cmds, list) else []

    @property
    def test_commands(self) -> list[str]:
        """Get build.test commands (smoke tests).

        Returns:
            List of test commands
        """
        test_cmds = self.build.get("test", [])
        if isinstance(test_cmds, str):
            return [test_cmds]
        return test_cmds if isinstance(test_cmds, list) else []

    @property
    def after_build_commands(self) -> list[str]:
        """Get build.after-build commands.

        Returns:
            List of commands to run after build (post-build)
        """
        cmds = self.build.get("after-build", [])
        if isinstance(cmds, str):
            return [cmds]
        return cmds if isinstance(cmds, list) else []

    @property
    def builder_name(self) -> str | None:
        """Get build.builder (explicit builder selection).

        Returns:
            Builder name ('local', 'docker', 'auto') or None for auto-detection
        """
        return self.build.get("builder")

    @property
    def toolchain_name(self) -> str | None:
        """Get build.toolchain (explicit toolchain selection).

        Returns:
            Toolchain name ('python', 'node', etc.) or None for auto-detection
        """
        return self.build.get("toolchain")

    @property
    def build_packages(self) -> list[str]:
        """Get build.packages (system packages for build)."""
        return self.build.get("packages", [])

    @property
    def ignore_patterns(self) -> list[str]:
        """Get build.ignore (patterns to exclude from deployment).

        Returns:
            List of glob patterns to ignore, empty list if not specified
        """
        patterns = self.build.get("ignore", [])
        if isinstance(patterns, list):
            return patterns
        return []

    @property
    def ignore_file(self) -> str | None:
        """Get build.ignore-file (file containing ignore patterns).

        Returns:
            Path to ignore file, or None if not specified
        """
        return self.build.get("ignore-file")

    @property
    def pip_install(self) -> list[str]:
        """Get build.pip-install (Python packages to install)."""
        return self.build.get("pip-install", [])

    # =========================================================================
    # [run] section - Maps to Procfile workers
    # =========================================================================

    @property
    def run(self) -> dict[str, Any]:
        """Get the [run] section."""
        return self._data.get("run", {})

    @property
    def run_packages(self) -> list[str]:
        """Get run.packages (system packages for runtime)."""
        return self.run.get("packages", [])

    @property
    def static_paths(self) -> dict[str, str]:
        """Get run.static (static file path mappings for reverse proxy).

        Returns:
            Dictionary mapping URL paths to filesystem paths
            e.g., {"/static": "static", "/media": "media"}
        """
        static = self.run.get("static", {})
        if isinstance(static, dict):
            return static
        return {}

    @property
    def healthcheck_path(self) -> str:
        """Get run.healthcheck (HTTP path for health checks).

        Returns:
            Health check path, e.g., "/health"
        """
        return self.run.get("healthcheck", "")

    @property
    def healthcheck_timeout(self) -> int:
        """Get run.healthcheck-timeout in seconds.

        Returns:
            Timeout in seconds for health checks
        """
        return int(self.run.get("healthcheck-timeout", 30))

    @property
    def before_run_commands(self) -> list[str]:
        """Get run.before-run commands.

        Returns:
            List of commands to run before starting the app
        """
        cmds = self.run.get("before-run", [])
        if isinstance(cmds, str):
            return [cmds]
        return cmds if isinstance(cmds, list) else []

    @property
    def start_command(self) -> str | list[str] | None:
        """Get run.start command(s).

        This maps to the primary process in a Procfile (usually 'web').

        Returns:
            Start command(s), or None if not specified
        """
        return self.run.get("start")

    @property
    def start_timeout(self) -> float | None:
        """Get run.start-timeout in seconds.

        This is the maximum time to wait for the app to start.
        If not specified, the server default (APP_START_TIMEOUT) is used.

        Returns:
            Timeout in seconds, or None to use server default
        """
        timeout = self.run.get("start-timeout")
        return float(timeout) if timeout is not None else None

    @property
    def named_workers(self) -> dict[str, str]:
        """Get run.workers.* (named worker definitions).

        Returns:
            Dictionary mapping worker names to commands
            e.g., {"worker": "celery -A app worker", "scheduler": "celery -A app beat"}
        """
        workers_section = self.run.get("workers", {})
        if isinstance(workers_section, dict):
            # Ensure all values are strings
            return {k: str(v) for k, v in workers_section.items()}
        return {}

    def get_workers_from_run_section(self) -> dict[str, str]:
        """Extract worker definitions from [run] section.

        This provides Procfile-compatible worker definitions from hop3.toml.
        Supports:
        - run.start -> 'web' worker
        - run.before-run -> 'prerun' worker
        - run.workers.* -> named workers (worker, scheduler, cron, etc.)

        Returns:
            Dictionary mapping worker names to commands
        """
        workers = {}

        # Map run.start to 'web' worker
        start_cmd = self.start_command
        if start_cmd:
            if isinstance(start_cmd, list):
                # Join multiple commands with &&
                workers["web"] = " && ".join(start_cmd)
            else:
                workers["web"] = start_cmd

        # Map run.before-run to 'prerun' worker
        before_run = self.before_run_commands
        if before_run:
            workers["prerun"] = " && ".join(before_run)

        # Add named workers from [run.workers] section
        # These can define worker, scheduler, cron, or any custom process type
        workers.update(self.named_workers)

        # NOTE: build.before-build is NOT added as a worker here because:
        # 1. It's already handled by deployer.py._run_hook() during deployment
        # 2. Adding it as a worker would cause it to run continuously as a daemon
        # The prebuild commands should only run once during the build phase

        return workers

    # =========================================================================
    # [env] section
    # =========================================================================

    @property
    def env(self) -> dict[str, Any]:
        """Get the [env] section (environment variables)."""
        return self._data.get("env", {})

    # =========================================================================
    # [port] section
    # =========================================================================

    @property
    def port(self) -> dict[str, Any]:
        """Get the [port] section."""
        return self._data.get("port", {})

    # =========================================================================
    # [docker] section
    # =========================================================================

    @property
    def docker(self) -> dict[str, Any]:
        """Get the [docker] section."""
        return self._data.get("docker", {})

    @property
    def docker_port(self) -> int | None:
        """Get docker.port (container port for Docker deployments).

        Returns:
            Port number if specified, None otherwise
        """
        port = self.docker.get("port")
        return int(port) if port is not None else None

    # =========================================================================
    # [[addons]] section (backing services)
    # =========================================================================

    @property
    def addons(self) -> list[dict[str, Any]]:
        """Get the [[addons]] sections (backing service dependencies).

        Also checks [[provider]] for backwards compatibility.

        Returns:
            List of addon definitions, each with at least a 'type' key
        """
        # Check both names for backwards compatibility
        addons = self._data.get("addons", [])
        if not addons:
            addons = self._data.get("provider", [])
        return addons

    def get_addon_types(self) -> list[str]:
        """Get list of addon types required by this app.

        Returns:
            List of addon type names (e.g., ['postgres', 'redis'])
        """
        return [
            addon_type
            for addon in self.addons
            if (addon_type := addon.get("type")) is not None
        ]

    # =========================================================================
    # [[provider]] section (deprecated, use [[addons]])
    # =========================================================================

    @property
    def providers(self) -> list[dict[str, Any]]:
        """Get the [[provider]] sections (list of service providers).

        Deprecated: Use `addons` property instead.
        """
        return self._data.get("provider", [])

    # =========================================================================
    # Utility methods
    # =========================================================================

    def has_section(self, section_name: str) -> bool:
        """Check if a section exists in the configuration.

        Args:
            section_name: Name of the section (e.g., 'run', 'build')

        Returns:
            True if the section exists and is not empty
        """
        return section_name in self._data and bool(self._data[section_name])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all configuration data
        """
        return {
            "config_path": str(self.config_path) if self.config_path else None,
            "metadata": self.metadata,
            "build": self.build,
            "run": self.run,
            "env": self.env,
            "port": self.port,
            "docker": self.docker,
            "addons": self.addons,
            "providers": self.providers,  # Deprecated, kept for compatibility
            "workers": self.get_workers_from_run_section(),
        }

    def __repr__(self) -> str:
        if self.config_path:
            return f"<Hop3Config {self.config_path}>"
        return "<Hop3Config from_str>"
