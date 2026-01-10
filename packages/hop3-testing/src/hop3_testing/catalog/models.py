# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Data models for test definitions.

These models define the schema for test.toml files used to describe
deployment tests, demos, and tutorials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal


class Tier(str, Enum):
    """Test execution time tier.

    Used to select which tests to run in different modes:
    - fast: Run in dev mode, CI
    - medium: Run in CI, nightly
    - slow: Run in nightly, release
    - very_slow: Run only in release validation
    """

    FAST = "fast"  # <10s
    MEDIUM = "medium"  # <2min
    SLOW = "slow"  # <10min
    VERY_SLOW = "very-slow"  # >10min


class Priority(str, Enum):
    """Test priority level.

    Used to determine which tests are critical:
    - P0: Must pass for any release (critical paths)
    - P1: Should pass for release (important coverage)
    - P2: Nice to have (edge cases, exotic configs)
    """

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class Category(str, Enum):
    """Test category.

    Determines how the test is executed:
    - deployment: Deploy an app and validate it works
    - demo: Run a demo script or declarative demo
    - tutorial: Execute tutorial via validoc
    """

    DEPLOYMENT = "deployment"
    DEMO = "demo"
    TUTORIAL = "tutorial"


class TargetType(str, Enum):
    """Where a test can run.

    - local: Developer machine (no full server)
    - docker: Docker container with Hop3
    - remote: Remote server via SSH
    """

    LOCAL = "local"
    DOCKER = "docker"
    REMOTE = "remote"


@dataclass
class TestRequirements:
    """Requirements for running a test."""

    targets: list[TargetType] = field(default_factory=lambda: [TargetType.DOCKER])
    """Which target types can run this test."""

    services: list[str] = field(default_factory=list)
    """Required services (e.g., postgresql, redis, mysql)."""

    network: Literal["isolated", "internet"] = "isolated"
    """Network access requirements."""

    dns: Literal["none", "static", "wildcard"] = "none"
    """DNS requirements (none, static IP, wildcard domain)."""

    def can_run_on(self, target_type: TargetType) -> bool:
        """Check if test can run on given target type."""
        return target_type in self.targets

    def needs_service(self, service: str) -> bool:
        """Check if test requires a specific service."""
        return service in self.services


@dataclass
class ValidationExpect:
    """Expected outcome for a validation check."""

    status: int | None = None
    """Expected HTTP status code."""

    contains: str | None = None
    """String that response body should contain."""

    json: dict[str, Any] | None = None
    """JSON fields to validate in response."""

    stdout: str | None = None
    """Exact expected stdout."""

    stdout_contains: str | None = None
    """String that stdout should contain."""

    exit_code: int | None = None
    """Expected command exit code."""

    all_blocks_pass: bool | None = None
    """For validoc: all blocks should pass."""


@dataclass
class Validation:
    """A single validation check."""

    type: Literal["http", "command", "script", "demo-script", "validoc"]
    """Type of validation to perform."""

    path: str | None = None
    """Path for HTTP validation or script path."""

    run: str | None = None
    """Command to run for command validation."""

    url: str | None = None
    """Full URL for HTTP validation (overrides path)."""

    method: str = "GET"
    """HTTP method for HTTP validation."""

    timeout: int = 30
    """Timeout in seconds for this validation."""

    expect: ValidationExpect = field(default_factory=ValidationExpect)
    """Expected outcome."""


@dataclass
class DeploymentConfig:
    """Configuration for deployment tests."""

    path: str = "."
    """Path to app directory (relative to test.toml)."""

    type: str | None = None
    """App type hint (python, nodejs, etc.)."""

    env_vars: dict[str, str] = field(default_factory=dict)
    """Environment variables to set during deployment."""


@dataclass
class DemoStep:
    """A step in a declarative demo."""

    action: Literal["deploy", "wait", "validate", "destroy", "command"]
    """Action to perform."""

    # For deploy action
    app_path: str | None = None
    app_name: str | None = None

    # For wait action
    seconds: int = 5

    # For validate action
    validation_type: str | None = None
    url: str | None = None
    expect_status: int | None = None
    expect_contains: str | None = None

    # For command action
    run: str | None = None
    expect_exit_code: int | None = None


@dataclass
class DemoConfig:
    """Configuration for demo tests."""

    script: str | None = None
    """Path to demo script (for script-based demos)."""

    type: Literal["script", "declarative"] = "script"
    """Demo type: script runs a Python file, declarative uses steps."""

    steps: list[DemoStep] = field(default_factory=list)
    """Steps for declarative demos."""


@dataclass
class TutorialConfig:
    """Configuration for tutorial tests."""

    path: str
    """Path to tutorial markdown file."""

    runner: str = "validoc"
    """Tutorial runner to use."""


@dataclass
class TestMetadata:
    """Optional metadata about the test."""

    author: str | None = None
    """Test author."""

    since: str | None = None
    """Minimum Hop3 version required."""

    covers: list[str] = field(default_factory=list)
    """Tags describing what this test covers."""

    language: str | None = None
    """Programming language (for tutorials)."""

    framework: str | None = None
    """Framework (for tutorials)."""


@dataclass
class TestDefinition:
    """Complete test definition parsed from test.toml."""

    name: str
    """Unique test identifier."""

    category: Category
    """Test category (deployment, demo, tutorial)."""

    tier: Tier
    """Execution time tier."""

    priority: Priority
    """Test priority."""

    requirements: TestRequirements
    """Requirements for running this test."""

    validations: list[Validation] = field(default_factory=list)
    """Validation checks to perform after deployment."""

    # Category-specific configs (only one is set based on category)
    deployment: DeploymentConfig | None = None
    demo: DemoConfig | None = None
    tutorial: TutorialConfig | None = None

    # Optional fields
    description: str | None = None
    """Human-readable description."""

    metadata: TestMetadata = field(default_factory=TestMetadata)
    """Optional metadata."""

    # Runtime info (set by loader, not from TOML)
    source_path: Path | None = None
    """Path to the test.toml file."""

    def can_run_on(self, target_type: TargetType) -> bool:
        """Check if this test can run on given target type."""
        return self.requirements.can_run_on(target_type)

    def needs_service(self, service: str) -> bool:
        """Check if this test needs a specific service."""
        return self.requirements.needs_service(service)

    @property
    def app_path(self) -> Path | None:
        """Get the application path for this test."""
        if self.source_path is None:
            return None

        if self.deployment:
            return self.source_path.parent / self.deployment.path
        if self.demo and self.demo.type == "declarative":
            # For declarative demos, look for app in steps
            for step in self.demo.steps:
                if step.action == "deploy" and step.app_path:
                    return self.source_path.parent / step.app_path
        return self.source_path.parent

    def __repr__(self) -> str:
        return (
            f"TestDefinition(name={self.name!r}, "
            f"category={self.category.value}, "
            f"tier={self.tier.value}, "
            f"priority={self.priority.value})"
        )
