# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Loader for test.toml files."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .models import (
    Category,
    DemoConfig,
    DemoStep,
    DeploymentConfig,
    Priority,
    TargetType,
    TestDefinition,
    TestMetadata,
    TestRequirements,
    Tier,
    TutorialConfig,
    Validation,
    ValidationExpect,
)


class TestDefinitionError(Exception):
    """Error loading or validating a test definition."""

    def __init__(self, message: str, path: Path | None = None):
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


def load_test_definition(path: Path) -> TestDefinition:
    """Parse a test.toml file into a TestDefinition.

    Args:
        path: Path to the test.toml file

    Returns:
        Parsed TestDefinition

    Raises:
        TestDefinitionError: If the file is invalid or missing required fields
    """
    if not path.exists():
        msg = "File not found"
        raise TestDefinitionError(msg, path)

    try:
        with Path(path).open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        msg = f"Invalid TOML: {e}"
        raise TestDefinitionError(msg, path) from e

    try:
        return _parse_test_definition(data, path)
    except KeyError as e:
        msg = f"Missing required field: {e}"
        raise TestDefinitionError(msg, path) from e
    except ValueError as e:
        raise TestDefinitionError(str(e), path) from e


def _parse_test_definition(data: dict[str, Any], path: Path) -> TestDefinition:
    """Parse the TOML data into a TestDefinition."""
    test_section = data.get("test", {})

    # Required fields
    name = test_section["name"]
    category = Category(test_section["category"])
    tier = Tier(test_section["tier"])
    priority = Priority(test_section["priority"])

    # Requirements
    requirements = _parse_requirements(test_section.get("requirements", {}))

    # Metadata
    metadata = _parse_metadata(test_section.get("metadata", {}))

    # Category-specific config
    deployment = _parse_deployment(data["deployment"]) if "deployment" in data else None
    demo = _parse_demo(data["demo"]) if "demo" in data else None
    tutorial = _parse_tutorial(data["tutorial"]) if "tutorial" in data else None

    # Validations
    validations = [_parse_validation(v) for v in data.get("validations", [])]

    return TestDefinition(
        name=name,
        category=category,
        tier=tier,
        priority=priority,
        requirements=requirements,
        validations=validations,
        deployment=deployment,
        demo=demo,
        tutorial=tutorial,
        description=test_section.get("description"),
        metadata=metadata,
        source_path=path,
    )


def _parse_requirements(data: dict[str, Any]) -> TestRequirements:
    """Parse requirements section."""
    targets = [TargetType(t) for t in data.get("targets", ["docker"])]

    return TestRequirements(
        targets=targets,
        services=data.get("services", []),
        network=data.get("network", "isolated"),
        dns=data.get("dns", "none"),
    )


def _parse_metadata(data: dict[str, Any]) -> TestMetadata:
    """Parse metadata section."""
    return TestMetadata(
        author=data.get("author"),
        since=data.get("since"),
        covers=data.get("covers", []),
        language=data.get("language"),
        framework=data.get("framework"),
    )


def _parse_deployment(data: dict[str, Any]) -> DeploymentConfig:
    """Parse deployment section."""
    return DeploymentConfig(
        path=data.get("path", "."),
        type=data.get("type"),
        env_vars=data.get("env_vars", {}),
    )


def _parse_demo(data: dict[str, Any]) -> DemoConfig:
    """Parse demo section."""
    demo_type = data.get("type", "script")
    steps = []

    if demo_type == "declarative" and "steps" in data:
        steps = [_parse_demo_step(s) for s in data["steps"]]

    return DemoConfig(
        script=data.get("script"),
        type=demo_type,
        steps=steps,
    )


def _parse_demo_step(data: dict[str, Any]) -> DemoStep:
    """Parse a single demo step."""
    return DemoStep(
        action=data["action"],
        app_path=data.get("app_path"),
        app_name=data.get("app_name"),
        seconds=data.get("seconds", 5),
        validation_type=data.get("type"),
        url=data.get("url"),
        expect_status=data.get("expect_status"),
        expect_contains=data.get("expect_contains"),
        run=data.get("run"),
        expect_exit_code=data.get("expect_exit_code"),
    )


def _parse_tutorial(data: dict[str, Any]) -> TutorialConfig:
    """Parse tutorial section."""
    return TutorialConfig(
        path=data["path"],
        runner=data.get("runner", "validoc"),
    )


def _parse_validation(data: dict[str, Any]) -> Validation:
    """Parse a single validation."""
    expect_data = data.get("expect", {})
    expect = ValidationExpect(
        status=expect_data.get("status"),
        contains=expect_data.get("contains"),
        json=expect_data.get("json"),
        stdout=expect_data.get("stdout"),
        stdout_contains=expect_data.get("stdout_contains"),
        exit_code=expect_data.get("exit_code"),
        all_blocks_pass=expect_data.get("all_blocks_pass"),
    )

    return Validation(
        type=data["type"],
        path=data.get("path"),
        run=data.get("run"),
        url=data.get("url"),
        method=data.get("method", "GET"),
        timeout=data.get("timeout", 30),
        expect=expect,
    )


def _infer_app_type(app_path: Path) -> str | None:
    """Infer app type from files present."""
    if (app_path / "requirements.txt").exists() or (
        app_path / "pyproject.toml"
    ).exists():
        return "python"
    if (app_path / "package.json").exists():
        return "nodejs"
    if (app_path / "go.mod").exists():
        return "golang"
    if (app_path / "Gemfile").exists():
        return "ruby"
    return None


def _read_description_from_readme(app_path: Path) -> str | None:
    """Read description from README.md first heading."""
    readme_path = app_path / "README.md"
    if not readme_path.exists():
        return None
    with readme_path.open() as f:
        first_line = f.readline().strip()
        if first_line.startswith("#"):
            return first_line.lstrip("#").strip()
    return None


def _build_validations_from_app(app_path: Path) -> list[Validation]:
    """Build validation list from app files."""
    validations = []
    if (app_path / "Procfile").exists():
        validations.append(
            Validation(type="http", path="/", expect=ValidationExpect(status=200))
        )
    if (app_path / "check.py").exists():
        validations.append(
            Validation(
                type="script", path="check.py", expect=ValidationExpect(exit_code=0)
            )
        )
    return validations


def generate_test_definition_from_app(
    app_path: Path,
    name: str | None = None,
) -> TestDefinition:
    """Generate a TestDefinition from an app directory without test.toml.

    This provides backwards compatibility with existing test apps that don't
    have a test.toml file. The definition is inferred from the app structure.

    For proper test categorization, apps should have a test.toml file with
    explicit category, tier, and priority settings.

    Args:
        app_path: Path to the application directory
        name: Override app name (default: directory name)

    Returns:
        Generated TestDefinition with default settings
    """
    app_name = name or app_path.name

    description = _read_description_from_readme(app_path)
    app_type = _infer_app_type(app_path)
    validations = _build_validations_from_app(app_path)

    # Build covers tags from inferred app type
    covers = []
    if app_type:
        covers.append(app_type)

    return TestDefinition(
        name=app_name,
        category=Category.DEPLOYMENT,
        tier=Tier.FAST,
        priority=Priority.P1,
        requirements=TestRequirements(
            targets=[TargetType.DOCKER, TargetType.REMOTE],
        ),
        validations=validations,
        deployment=DeploymentConfig(
            path=".",
            type=app_type,
        ),
        description=description,
        metadata=TestMetadata(covers=covers),
        source_path=app_path / "test.toml",  # Virtual path
    )
