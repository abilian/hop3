# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Pydantic schema for hop3.toml validation.

This module defines Pydantic models that validate hop3.toml configuration files.
The schema enforces:
- Known sections only (unknown sections are rejected)
- Correct types for all fields
- Valid values where applicable

When validation fails, clear error messages are provided to help users
fix their configuration.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class MetadataSection(BaseModel):
    """[metadata] section - Application identity."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    version: str | None = None
    title: str | None = None
    description: str | None = None
    author: str | None = None
    license: str | None = None


class BuildSection(BaseModel):
    """[build] section - Build-time configuration."""

    model_config = ConfigDict(extra="forbid")

    builder: str | None = Field(
        default=None,
        description="Builder to use: 'local', 'docker', or 'auto' (default)",
    )
    toolchain: str | None = Field(
        default=None,
        description="Language toolchain: 'python', 'node', 'ruby', 'go', 'rust', etc.",
    )
    before_build: str | list[str] | None = Field(
        default=None,
        alias="before-build",
        description="Commands to run before build",
    )
    after_build: str | list[str] | None = Field(
        default=None,
        alias="after-build",
        description="Commands to run after build (post-build)",
    )
    build: str | list[str] | None = Field(
        default=None,
        description="Build commands",
    )
    test: str | list[str] | None = Field(
        default=None,
        description="Test/smoke test commands",
    )
    packages: list[str] | None = Field(
        default=None,
        description="System packages required for build",
    )
    pip_install: list[str] | None = Field(
        default=None,
        alias="pip-install",
        description="Python packages to install",
    )
    ignore: list[str] | None = Field(
        default=None,
        description="Patterns to ignore when deploying",
    )
    ignore_file: str | None = Field(
        default=None,
        alias="ignore-file",
        description="File containing ignore patterns",
    )

    @field_validator("builder")
    @classmethod
    def validate_builder(cls, v: str | None) -> str | None:
        if v is not None:
            valid_builders = {"auto", "local", "docker"}
            if v.lower() not in valid_builders:
                msg = f"Invalid builder '{v}'. Must be one of: {', '.join(valid_builders)}"
                raise ValueError(msg)
        return v


class WorkersSection(BaseModel):
    """[run.workers] section - Named worker processes."""

    model_config = ConfigDict(extra="allow")  # Allow any worker names


class RunSection(BaseModel):
    """[run] section - Runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    start: str | list[str] | None = Field(
        default=None,
        description="Start command for the web process",
    )
    before_run: str | list[str] | None = Field(
        default=None,
        alias="before-run",
        description="Commands to run before starting the app",
    )
    workers: dict[str, str] | None = Field(
        default=None,
        description="Named worker processes (worker, scheduler, cron, etc.)",
    )
    start_timeout: int | float | None = Field(
        default=None,
        alias="start-timeout",
        description="Maximum time to wait for app to start (seconds)",
    )
    packages: list[str] | None = Field(
        default=None,
        description="System packages required at runtime",
    )
    static: dict[str, str] | None = Field(
        default=None,
        description="Static file path mappings (URL path -> filesystem path)",
    )
    healthcheck: str | None = Field(
        default=None,
        description="Health check HTTP path",
    )
    healthcheck_timeout: int | None = Field(
        default=None,
        alias="healthcheck-timeout",
        description="Health check timeout in seconds",
    )


class PortConfig(BaseModel):
    """Port configuration for a single port (full format)."""

    model_config = ConfigDict(extra="forbid")

    container: int | None = Field(
        default=None,
        description="Internal container port",
    )
    public: bool = Field(
        default=True,
        description="Whether the port is publicly accessible",
    )
    https: bool = Field(
        default=True,
        description="Whether HTTPS is enabled",
    )


# Port can be either a simple int or a full PortConfig
PortValue = int | PortConfig


class DockerSection(BaseModel):
    """[docker] section - Docker-specific configuration."""

    model_config = ConfigDict(extra="forbid")

    port: int | None = Field(
        default=None,
        description="Container port for Docker deployments",
    )
    build_args: dict[str, str] | None = Field(
        default=None,
        alias="build-args",
        description="Docker build arguments",
    )


class HealthcheckSection(BaseModel):
    """[healthcheck] section - Health monitoring configuration."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = Field(
        default=None,
        description="Health check HTTP path",
    )
    interval: int | None = Field(
        default=None,
        description="Check interval in seconds",
    )
    timeout: int | None = Field(
        default=None,
        description="Timeout in seconds",
    )
    retries: int | None = Field(
        default=None,
        description="Number of retries before marking unhealthy",
    )


class BackupSection(BaseModel):
    """[backup] section - Backup configuration."""

    model_config = ConfigDict(extra="forbid")

    paths: list[str] | None = Field(
        default=None,
        description="Directories to include in backups",
    )
    exclude: list[str] | None = Field(
        default=None,
        description="Patterns to exclude from backups",
    )


class AddonConfig(BaseModel):
    """Single addon/provider configuration."""

    model_config = ConfigDict(extra="allow")  # Allow addon-specific options

    # 'type' is the modern field name, 'name' is deprecated but still supported
    type: str | None = Field(
        default=None,
        description="Addon type: 'postgres', 'mysql', 'redis', etc.",
    )
    name: str | None = Field(
        default=None,
        description="Addon instance name (legacy: also used as type in older configs)",
    )


class Hop3TomlSchema(BaseModel):
    """Complete hop3.toml schema with validation.

    This schema validates the entire hop3.toml file and rejects unknown
    top-level sections. Each section has its own validation rules.

    Example hop3.toml:
        [metadata]
        id = "myapp"

        [build]
        builder = "local"
        before-build = "npm install"

        [run]
        start = "gunicorn app:app -b 0.0.0.0:$PORT"
        before-run = ["python manage.py migrate"]

        [run.workers]
        worker = "celery -A app worker"

        [env]
        DEBUG = "false"
    """

    model_config = ConfigDict(
        extra="forbid",  # Reject unknown top-level sections
        populate_by_name=True,  # Allow both alias and field name
    )

    metadata: MetadataSection | None = None
    build: BuildSection | None = None
    run: RunSection | None = None
    env: dict[str, Any] | None = None
    port: dict[str, PortValue] | None = None
    docker: DockerSection | None = None
    healthcheck: HealthcheckSection | None = None
    backup: BackupSection | None = None
    addons: list[AddonConfig] | None = None
    provider: list[AddonConfig] | None = Field(
        default=None,
        description="Deprecated: use [[addons]] instead",
    )


class Hop3TomlValidationError(Exception):
    """Raised when hop3.toml validation fails."""

    def __init__(self, errors: list[dict[str, Any]], raw_data: dict[str, Any]) -> None:
        self.errors = errors
        self.raw_data = raw_data
        self.message = self._format_message()
        super().__init__(self.message)

    def _format_message(self) -> str:
        """Format validation errors into a user-friendly message."""
        lines = ["Invalid hop3.toml configuration:"]

        for error in self.errors:
            loc = " -> ".join(str(x) for x in error.get("loc", []))
            msg = error.get("msg", "Unknown error")
            error_type = error.get("type", "")

            if error_type == "extra_forbidden":
                # Make "extra fields not permitted" errors more helpful
                lines.append(f"  - Unknown field '{loc}'")
                lines.append("    Did you mean one of the valid options?")
            else:
                lines.append(f"  - {loc}: {msg}")

        # Add hint for common mistakes
        if any("extra_forbidden" in str(e.get("type", "")) for e in self.errors):
            lines.append("")
            lines.append("Hint: Check the hop3.toml reference for valid fields:")
            lines.append("  https://hop3.cloud/reference/config/")

        return "\n".join(lines)


def validate_hop3_toml(data: dict[str, Any]) -> Hop3TomlSchema:
    """Validate hop3.toml data against the schema.

    Args:
        data: Parsed TOML data as dictionary

    Returns:
        Validated Hop3TomlSchema instance

    Raises:
        Hop3TomlValidationError: If validation fails with detailed error info
    """
    try:
        return Hop3TomlSchema.model_validate(data)
    except ValidationError as e:
        raise Hop3TomlValidationError(e.errors(), data) from None


def get_json_schema() -> dict[str, Any]:
    """Generate JSON Schema for hop3.toml.

    This can be used by IDEs and editors for autocompletion and validation.

    Returns:
        JSON Schema as dictionary
    """
    return Hop3TomlSchema.model_json_schema()
