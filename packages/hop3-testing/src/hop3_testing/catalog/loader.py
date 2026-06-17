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
        tier=tier,
        priority=priority,
        requirements=requirements,
        validations=validations,
        deployment=deployment,
        demo=demo,
        tutorial=tutorial,
        description=test_section.get("description"),
        metadata=metadata,
        # Apps under apps/bad/ are "bad recipes": negative tests expected to
        # fail. A config flag can also opt any app in.
        expects_failure=(
            bool(test_section.get("expects-failure", False)) or _under_bad_dir(path)
        ),
        source_path=path,
    )


def _under_bad_dir(path: Path | None) -> bool:
    """True for apps under apps/bad/ (the expected-to-fail "bad recipes")."""
    return path is not None and "/apps/bad/" in f"/{path.as_posix()}"


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
        builder=data.get("builder"),
        toolchain=data.get("toolchain"),
        spec=data.get("spec"),
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
    """Parse a single validation.

    Accepts two shapes:

    - Legacy (`test.toml`): nested `expect = {status = ..., contains = ...}`.
    - New (`hop3.toml [[test.validations]]`): status / contains at top level,
      no need for a nested `[validations.expect]` table just to hold two fields.
      Type defaults to "http" when omitted.

    When both shapes are present (contrived), top-level fields win.
    """
    expect_data = data.get("expect", {})

    def _pick(key: str):
        # Top-level wins over nested `expect` when both are set.
        return data[key] if key in data else expect_data.get(key)

    # status-in (list) coexists with status (scalar). Both picked up
    # from either top-level or nested `expect`. Runner prefers
    # status_in when set.
    status_in_raw = _pick("status_in") or _pick("status-in")
    status_in = (
        [int(s) for s in status_in_raw] if isinstance(status_in_raw, list) else None
    )
    expect = ValidationExpect(
        status=_pick("status"),
        status_in=status_in,
        contains=_pick("contains"),
        json=_pick("json"),
        stdout=_pick("stdout"),
        stdout_contains=_pick("stdout_contains"),
        exit_code=_pick("exit_code"),
        all_blocks_pass=_pick("all_blocks_pass"),
    )

    return Validation(
        type=data.get("type", "http"),
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


# Normalise inferred app types to canonical toolchain tags (see TestMetadata).
_TOOLCHAIN_MAP = {"nodejs": "node", "golang": "go"}


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

    # Build covers tags from inferred app type
    covers = []
    if app_type:
        covers.append(app_type)

    # Derive builder / toolchain / spec for Procfile-only apps.
    builder = "native"  # Procfile-only apps run via uWSGI (local builder)
    toolchain = _TOOLCHAIN_MAP.get(app_type, app_type) if app_type else None
    spec = _spec_from_source(app_path) or "procfile"

    # Determine demo vs deployment by checking for demo-script.py
    demo_config = None
    deployment_config = None
    validations: list[Validation] = []
    if (app_path / "demo-script.py").exists():
        demo_config = DemoConfig(script="demo-script.py", type="script")
        spec = "demo"  # demo-script.py is the config source, not Procfile
    else:
        deployment_config = DeploymentConfig(
            path=deployment_path,
            type=app_type,
        )
        # Build validations from app files (Procfile -> HTTP check, check.py -> script)
        validations = _build_validations_from_app(actual_app_path)

    return TestDefinition(
        name=app_name,
        tier=Tier.FAST,
        priority=Priority.P1,
        requirements=TestRequirements(
            targets=[TargetType.DOCKER, TargetType.REMOTE],
        ),
        validations=validations,
        deployment=deployment_config,
        demo=demo_config,
        description=description,
        metadata=TestMetadata(covers=covers, builder=builder, toolchain=toolchain, spec=spec),
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


def _builder_from_hop3_toml(data: dict[str, Any]) -> str | None:
    """Derive the coverage-tag builder from hop3.toml [build] + [nix].

    Maps ``[build].builder`` to the tag values used by coverage selection:
    - ``local`` → ``native`` (uWSGI)
    - ``docker`` → ``docker``
    - ``nix`` → ``nix`` or ``nix-template`` (depending on ``[nix].template``)
    - missing → ``None``
    """
    build_section = data.get("build") or {}
    raw = build_section.get("builder", "")
    if raw == "local":
        return "native"
    if raw == "docker":
        return "docker"
    if raw == "nix":
        nix_section = data.get("nix") or {}
        return "nix-template" if "template" in nix_section else "nix"
    return None


def _toolchain_from_hop3_toml(data: dict[str, Any]) -> str | None:
    """Toolchain from ``[build].toolchain``, if explicitly set."""
    build_section = data.get("build") or {}
    return build_section.get("toolchain") or None


def _spec_from_source(app_path: Path) -> str | None:
    """Configuration format from the source file present.

    - ``hop3.toml`` → ``hop3toml``
    - ``Procfile`` (no hop3.toml) → ``procfile``
    - ``demo-script.py`` (no hop3.toml) → ``demo``
    - tutorial markdown → ``tutorial`` (set by the tutorial loader)
    """
    if (app_path / "hop3.toml").exists():
        return "hop3toml"
    if (app_path / "Procfile").exists():
        return "procfile"
    return None


def _derive_unique_name(app_path: Path) -> str:
    """Derive a unique name from the app path.

    For generic directory names like 'app', include parent directory.
    Examples:
        demos/demo28/app -> demo28-app
        apps/docker-apps/wordpress -> wordpress
        demos/demo28 -> demo28
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


_TARGET_MAP = {"docker": TargetType.DOCKER, "remote": TargetType.REMOTE}


def _copy_coverage_overrides(section: dict[str, Any], out: dict[str, Any]) -> None:
    """Copy explicit coverage-tag overrides (builder/toolchain/spec) from a
    `[test]` section into ``out``, when present."""
    for key in ("builder", "toolchain", "spec"):
        if key in section:
            out[key] = section[key]


def _overrides_from_hop3_test(section: dict[str, Any]) -> dict[str, Any]:
    """Extract TestDefinition overrides from a `[test]` section in hop3.toml."""
    out: dict[str, Any] = {}
    if "tier" in section:
        out["tier"] = Tier(section["tier"])
    if "priority" in section:
        out["priority"] = Priority(section["priority"])
    if "author" in section:
        out["author"] = section["author"]
    if "covers" in section:
        out["covers_prefix"] = list(section["covers"])
    if "targets" in section:
        out["targets"] = [_TARGET_MAP[t] for t in section["targets"]]
    if "validations" in section:
        out["validations"] = [_parse_validation(v) for v in section["validations"]]
    if "expects-failure" in section:
        out["expects_failure"] = bool(section["expects-failure"])
    _copy_coverage_overrides(section, out)
    return out


def _overrides_from_legacy_test_toml(data: dict[str, Any]) -> dict[str, Any]:
    """Extract TestDefinition overrides from a legacy standalone test.toml."""
    section = data.get("test", {})
    out: dict[str, Any] = {}
    if "tier" in section:
        out["tier"] = Tier(section["tier"])
    if "priority" in section:
        out["priority"] = Priority(section["priority"])
    if "description" in section:
        out["description"] = section["description"]
    if "validations" in data:
        out["validations"] = [_parse_validation(v) for v in data["validations"]]
    if "expects-failure" in section:
        out["expects_failure"] = bool(section["expects-failure"])
    _copy_coverage_overrides(section, out)
    metadata = section.get("metadata", {})
    if "covers" in metadata:
        out["covers_prefix"] = list(metadata["covers"])
    if "author" in metadata:
        out["author"] = metadata["author"]
    return out


def generate_test_definition_from_hop3_toml(
    app_path: Path,
    hop3_data: dict[str, Any],
    test_toml_data: dict[str, Any] | None = None,
) -> TestDefinition:
    """Generate a TestDefinition from hop3.toml, optionally merging test.toml metadata.

    Preferred source is the `[test]` section in hop3.toml (canonical
    since 2026-04-21). A standalone test.toml is kept as a fallback for
    demos / tutorials / negative-test cases where hop3.toml is absent or
    doesn't have a `[test]` section.
    """
    metadata_section = hop3_data.get("metadata", {})
    base_name = metadata_section.get("id") or _derive_unique_name(app_path)
    app_title = metadata_section.get("title", base_name)

    services = _extract_services_from_hop3_toml(hop3_data)
    env_vars = _extract_env_vars_from_hop3_toml(hop3_data)
    healthcheck_path = _extract_healthcheck_from_hop3_toml(hop3_data)
    deployment_type = _get_deployment_type_from_hop3_toml(hop3_data)

    base_covers = ["docker" if deployment_type == "docker" else "native", *services]

    hop3_test_section = hop3_data.get("test") or {}
    if hop3_test_section:
        overrides = _overrides_from_hop3_test(hop3_test_section)
    elif test_toml_data:
        overrides = _overrides_from_legacy_test_toml(test_toml_data)
    else:
        overrides = {}

    # Tier is a display label only — no longer drives any timeout
    # (single 30-min budget applies to all builds + deploys).
    tier = overrides.get("tier", Tier.MEDIUM)
    priority = overrides.get("priority", Priority.P1)
    description = overrides.get("description", app_title)
    targets = overrides.get("targets", [TargetType.DOCKER, TargetType.REMOTE])
    covers = overrides.get("covers_prefix", []) + base_covers
    validations = overrides.get("validations") or [
        Validation(
            type="http",
            path=healthcheck_path,
            expect=ValidationExpect(status=200),
        )
    ]

    metadata_kwargs: dict[str, Any] = {"covers": covers}
    if "author" in overrides:
        metadata_kwargs["author"] = overrides["author"]
    # Derive builder / toolchain / spec from hop3.toml data (overridable via
    # explicit [test] fields for edge cases).
    metadata_kwargs["builder"] = overrides.get("builder") or _builder_from_hop3_toml(
        hop3_data
    )
    metadata_kwargs["toolchain"] = overrides.get(
        "toolchain"
    ) or _toolchain_from_hop3_toml(hop3_data)
    metadata_kwargs["spec"] = overrides.get("spec") or _spec_from_source(app_path)

    return TestDefinition(
        name=base_name,
        tier=tier,
        priority=priority,
        requirements=TestRequirements(targets=targets, services=services),
        validations=validations,
        deployment=DeploymentConfig(
            path=".",
            type=deployment_type,
            env_vars=env_vars,
        ),
        description=description,
        metadata=TestMetadata(**metadata_kwargs),
        # Bad recipes (apps/bad/**) are negative tests even when configured via
        # hop3.toml — match the standalone-test.toml path so they're xfail, not
        # red. An explicit [test] expects-failure flag still opts any app in.
        expects_failure=overrides.get("expects_failure", False)
        or _under_bad_dir(app_path),
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


def _read_markdown_title(md_path: Path) -> str | None:
    """Read a tutorial's description from its first markdown heading."""
    try:
        with md_path.open() as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()
    except OSError:
        return None
    return None


def generate_tutorial_test_definition(md_path: Path) -> TestDefinition:
    """Generate a TestDefinition for a literate tutorial markdown file.

    Tutorials live as ``docs/tutorials/<language>/<framework>.md`` (the source
    tree, where the validoc ``bash exec``/``output``/``file`` markers still
    exist) and are executed by ``validoc`` (see ``TutorialTestRunner``). The
    language is taken from the parent directory and the framework from the file
    stem.

    Args:
        md_path: Path to the tutorial markdown file.

    Returns:
        A tutorial TestDefinition (``category == "tutorial"``).
    """
    language = md_path.parent.name
    framework = md_path.stem
    covers = [c for c in (language, framework) if c]

    return TestDefinition(
        # P1 + slow so tutorials run in the nightly matrix (nightly = P0+P1,
        # tiers fast/medium/slow) alongside demos, not only in `release`.
        name=f"{language}/{framework}",
        tier=Tier.SLOW,
        priority=Priority.P1,
        requirements=TestRequirements(
            targets=[TargetType.DOCKER, TargetType.REMOTE],
        ),
        validations=[],
        tutorial=TutorialConfig(path=md_path.name, runner="validoc"),
        description=_read_markdown_title(md_path),
        metadata=TestMetadata(
            language=language,
            framework=framework,
            covers=covers,
            builder=None,  # tutorials don't use the builder system
            toolchain=language,  # parent dir name is the toolchain (python, go, etc.)
            spec="tutorial",
        ),
        source_path=md_path,
    )
