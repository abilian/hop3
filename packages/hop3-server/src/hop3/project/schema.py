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

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class MetadataSection(BaseModel):
    """[metadata] section - Application identity and catalog info."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    version: str | None = None
    title: str | None = None
    description: str | None = None
    author: str | None = None
    license: str | None = None
    name: str | None = None
    homepage: str | None = None
    categories: list[str] | None = None
    tags: list[str] | None = None


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
            valid_builders = {"auto", "local", "docker", "nix"}
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
    runtime: str | None = Field(
        default=None,
        description="Docker runtime: 'docker' (default) or 'docker-compose'",
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


class TestValidation(BaseModel):
    """A single [[test.validations]] entry — one HTTP check the test harness
    performs after the app is up.
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        default="http",
        description="Validation type. Currently only 'http' is supported.",
    )
    path: str = Field(default="/", description="URL path to probe.")
    status: int = Field(default=200, description="Expected HTTP status code.")
    contains: str | None = Field(
        default=None,
        description="If set, response body must contain this substring.",
    )


class TestSection(BaseModel):
    """[test] section — test-harness-specific fields.

    Everything the test harness needs that cannot be derived from the rest
    of hop3.toml. Fields like name / description / category / services /
    deployment type are derived (from metadata, build.builder, addons).

    Replaces the separate `test.toml` file — one source of truth per app.
    """

    model_config = ConfigDict(extra="forbid")

    priority: str | None = Field(
        default=None,
        description="Test priority: 'P0' | 'P1' | 'P2'. Selects which profile runs it.",
    )
    tier: str | None = Field(
        default=None,
        description=(
            "Test-tier label, used in reports only (no longer drives any "
            "timeout). Values: 'fast' | 'medium' | 'slow' | 'very-slow'."
        ),
    )
    targets: list[str] | None = Field(
        default=None,
        description="Test targets this app supports: 'docker' | 'remote'.",
    )
    author: str | None = None
    covers: list[str] | None = Field(
        default=None,
        description="Free-form tags listing what the test exercises.",
    )
    validations: list[TestValidation] | None = Field(
        default=None,
        description="HTTP checks beyond the single [healthcheck] endpoint.",
    )

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in {"P0", "P1", "P2"}:
            msg = f"Invalid test priority '{v}'. Must be one of: P0, P1, P2"
            raise ValueError(msg)
        return v

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str | None) -> str | None:
        if v is not None and v not in {"fast", "medium", "slow", "very-slow"}:
            msg = (
                f"Invalid test tier '{v}'. Must be one of: "
                "fast, medium, slow, very-slow"
            )
            raise ValueError(msg)
        return v

    @field_validator("targets")
    @classmethod
    def validate_targets(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        valid = {"docker", "remote"}
        for target in v:
            if target not in valid:
                msg = f"Invalid test target '{target}'. Must be one of: {sorted(valid)}"
                raise ValueError(msg)
        return v


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
    env: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Environment variables. "
            "Set _policy = 'override' to update existing values on redeploy."
        ),
    )
    port: dict[str, PortValue] | None = None
    docker: DockerSection | None = None
    healthcheck: HealthcheckSection | None = None
    backup: BackupSection | None = None
    static: dict[str, str] | None = Field(
        default=None,
        description="Static file path mappings (URL path -> filesystem path)",
    )
    addons: list[AddonConfig] | None = None
    provider: list[AddonConfig] | None = Field(
        default=None,
        description="Deprecated: use [[addons]] instead",
    )
    test: TestSection | None = Field(
        default=None,
        description=(
            "Test-harness metadata. Replaces the separate test.toml file — "
            "see TestSection for fields."
        ),
    )
    nix: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Nix template configuration for auto-generating hop3.nix. "
            "Requires [nix].template to be set. See ADR 008."
        ),
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
        # Cast ErrorDetails to dict[str, Any] for our error handler
        errors = cast("list[dict[str, Any]]", e.errors())
        raise Hop3TomlValidationError(errors, data) from None


def get_json_schema() -> dict[str, Any]:
    """Generate JSON Schema for hop3.toml.

    This can be used by IDEs and editors for autocompletion and validation.

    Returns:
        JSON Schema as dictionary
    """
    return Hop3TomlSchema.model_json_schema()
