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
        name: Override app name (default: derived from path)

    Returns:
        Generated TestDefinition with default settings
    """
    app_name = name or _derive_unique_name(app_path)

    # Check if actual app content is in an 'app/' subdirectory (common for demos)
    actual_app_path = app_path
    deployment_path = "."
    if (app_path / "app").is_dir():
        # Check if app/ has deployable files
        app_subdir = app_path / "app"
        if _is_deployable_app(app_subdir):
            actual_app_path = app_subdir
            deployment_path = "app"

    description = _read_description_from_readme(app_path)
    app_type = _infer_app_type(actual_app_path)
    validations = _build_validations_from_app(actual_app_path)

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
            path=deployment_path,
            type=app_type,
        ),
        description=description,
        metadata=TestMetadata(covers=covers),
        source_path=app_path / "test.toml",  # Virtual path
    )


def _is_deployable_app(path: Path) -> bool:
    """Check if a directory contains deployable app files."""
    # Check for common app markers
    markers = [
        "Procfile",
        "hop3.toml",
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "go.mod",
        "Gemfile",
        "Cargo.toml",
        "Dockerfile",
        "index.html",
    ]
    return any((path / marker).exists() for marker in markers)


def load_hop3_toml(app_path: Path) -> dict[str, Any] | None:
    """Load and parse hop3.toml from an app directory.

    Args:
        app_path: Path to the application directory

    Returns:
        Parsed hop3.toml data, or None if not found
    """
    hop3_toml = app_path / "hop3.toml"
    if not hop3_toml.exists():
        return None

    try:
        with hop3_toml.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError:
        return None


def _extract_services_from_hop3_toml(data: dict[str, Any]) -> list[str]:
    """Extract required services from hop3.toml addons section."""
    services = []
    for addon in data.get("addons", []):
        addon_type = addon.get("type")
        if addon_type:
            services.append(addon_type)
    return services


def _extract_env_vars_from_hop3_toml(data: dict[str, Any]) -> dict[str, str]:
    """Extract environment variables from hop3.toml."""
    return data.get("env", {})


def _extract_healthcheck_from_hop3_toml(data: dict[str, Any]) -> str:
    """Extract healthcheck path from hop3.toml."""
    healthcheck = data.get("healthcheck", {})
    return healthcheck.get("path", "/")


def _get_deployment_type_from_hop3_toml(data: dict[str, Any]) -> str:
    """Determine deployment type from hop3.toml build section.

    builder = "local" means native/uWSGI deployment
    Otherwise (no builder or builder = "docker") means Docker deployment
    """
    build_config = data.get("build", {})
    builder = build_config.get("builder", "")
    return "native" if builder == "local" else "docker"


def _infer_category_from_path_and_type(app_path: Path, deployment_type: str) -> Category:
    """Infer test category based on directory path and deployment type.

    Priority:
    1. Apps in demos/ -> DEMO (regardless of deployment type)
    2. Apps in test-apps/ -> DEPLOYMENT (regardless of deployment type)
    3. Apps in docker-apps/ -> DOCKER_APP
    4. Apps in native-apps/ -> NATIVE_APP
    5. Fallback: use deployment type
    """
    # Convert to string for easy checking
    path_str = str(app_path)

    # Check demos first - demos keep DEMO category regardless of deployment type
    if "/demos/" in path_str:
        return Category.DEMO

    # Check test-apps - these stay as DEPLOYMENT
    if "/test-apps/" in path_str:
        return Category.DEPLOYMENT

    # Check docker-apps and native-apps directories
    if "/docker-apps/" in path_str or path_str.endswith("/docker-apps"):
        return Category.DOCKER_APP
    if "/native-apps/" in path_str or path_str.endswith("/native-apps"):
        return Category.NATIVE_APP

    # Fallback: use deployment type if not in special directories
    if deployment_type == "docker":
        return Category.DOCKER_APP
    if deployment_type == "native":
        return Category.NATIVE_APP

    return Category.DEPLOYMENT


def _get_name_prefix_from_path(app_path: Path) -> str:
    """Get a name prefix based on source directory.

    Apps in apps/docker-apps get "docker:" prefix
    Apps in apps/native-apps get "native:" prefix
    Other apps get no prefix
    """
    path_str = str(app_path)

    if "/docker-apps/" in path_str or path_str.endswith("/docker-apps"):
        return "docker:"
    if "/native-apps/" in path_str or path_str.endswith("/native-apps"):
        return "native:"

    return ""


def _derive_unique_name(app_path: Path) -> str:
    """Derive a unique name from the app path.

    For generic directory names like 'app', include parent directory.
    Examples:
        demos/demo20/app -> demo20-app
        apps/docker-apps/wordpress -> wordpress
        demos/demo20 -> demo20
    """
    dir_name = app_path.name

    # Generic names that need parent context
    generic_names = {"app", "src", "web", "server", "application"}

    if dir_name.lower() in generic_names:
        parent_name = app_path.parent.name
        # Avoid generic parent names too
        if parent_name.lower() not in generic_names:
            return f"{parent_name}-{dir_name}"
        # Try grandparent
        grandparent_name = app_path.parent.parent.name
        return f"{grandparent_name}-{parent_name}-{dir_name}"

    return dir_name


def generate_test_definition_from_hop3_toml(
    app_path: Path,
    hop3_data: dict[str, Any],
    test_toml_data: dict[str, Any] | None = None,
) -> TestDefinition:
    """Generate a TestDefinition from hop3.toml, optionally merging test.toml metadata.

    Args:
        app_path: Path to the application directory
        hop3_data: Parsed hop3.toml data
        test_toml_data: Optional parsed test.toml data for test-specific metadata

    Returns:
        Generated TestDefinition
    """
    # Get app name from hop3.toml metadata or derive from path
    metadata_section = hop3_data.get("metadata", {})
    base_name = metadata_section.get("id") or _derive_unique_name(app_path)

    # Add prefix to make names unique between docker-apps and native-apps
    name_prefix = _get_name_prefix_from_path(app_path)
    app_name = f"{name_prefix}{base_name}"
    app_title = metadata_section.get("title", base_name)

    # Extract deployment info from hop3.toml
    services = _extract_services_from_hop3_toml(hop3_data)
    env_vars = _extract_env_vars_from_hop3_toml(hop3_data)
    healthcheck_path = _extract_healthcheck_from_hop3_toml(hop3_data)
    deployment_type = _get_deployment_type_from_hop3_toml(hop3_data)

    # Build covers tags
    covers = []
    if deployment_type == "docker":
        covers.append("docker")
    else:
        covers.append("native")

    # Add service tags
    covers.extend(services)

    # Determine category based on source path and deployment type
    category = _infer_category_from_path_and_type(app_path, deployment_type)

    # Default test-specific values (can be overridden by test.toml)
    tier = Tier.MEDIUM  # Docker apps typically take longer
    priority = Priority.P1
    description = app_title
    validations = []

    # Override with test.toml if available
    if test_toml_data:
        test_section = test_toml_data.get("test", {})
        if "tier" in test_section:
            tier = Tier(test_section["tier"])
        if "priority" in test_section:
            priority = Priority(test_section["priority"])
        if "category" in test_section:
            category = Category(test_section["category"])
        if "description" in test_section:
            description = test_section["description"]

        # Get validations from test.toml
        validations = [
            _parse_validation(v) for v in test_toml_data.get("validations", [])
        ]

        # Merge metadata
        test_metadata = test_section.get("metadata", {})
        if "covers" in test_metadata:
            covers = test_metadata["covers"] + covers

    # Build default HTTP validation if none specified
    if not validations:
        validations.append(
            Validation(
                type="http",
                path=healthcheck_path,
                expect=ValidationExpect(status=200),
            )
        )

    return TestDefinition(
        name=app_name,
        category=category,
        tier=tier,
        priority=priority,
        requirements=TestRequirements(
            targets=[TargetType.DOCKER, TargetType.REMOTE],
            services=services,
        ),
        validations=validations,
        deployment=DeploymentConfig(
            path=".",
            type=deployment_type,
            env_vars=env_vars,
        ),
        description=description,
        metadata=TestMetadata(covers=covers),
        source_path=app_path / "hop3.toml",
    )


def load_test_definition_smart(app_path: Path) -> TestDefinition:
    """Load test definition from an app directory, trying multiple sources.

    Priority:
    1. hop3.toml + test.toml (hop3.toml for deployment, test.toml for test metadata)
    2. test.toml only
    3. Generate from app structure

    Args:
        app_path: Path to the application directory

    Returns:
        TestDefinition from best available source
    """
    hop3_data = load_hop3_toml(app_path)
    test_toml_path = app_path / "test.toml"
    test_toml_data = None

    if test_toml_path.exists():
        try:
            with test_toml_path.open("rb") as f:
                test_toml_data = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            test_toml_data = None

    # Case 1: hop3.toml exists - use it as primary source
    if hop3_data:
        return generate_test_definition_from_hop3_toml(
            app_path, hop3_data, test_toml_data
        )

    # Case 2: test.toml only
    if test_toml_data:
        return _parse_test_definition(test_toml_data, test_toml_path)

    # Case 3: Generate from structure
    return generate_test_definition_from_app(app_path)
