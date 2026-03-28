# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test commands (package, system, apps)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import click

from hop3_testing.catalog import Catalog
from hop3_testing.catalog.loader import (
    generate_test_definition_from_app,
    load_test_definition_smart,
)
from hop3_testing.cli.runners import run_app_tests, run_system_tests
from hop3_testing.results import ConsoleReporter
from hop3_testing.runners import DeploymentTestRunner
from hop3_testing.selector import Selector, get_mode_config
from hop3_testing.targets import DockerTarget, RemoteTarget
from hop3_testing.targets.config import DeploymentConfig, DockerConfig, RemoteConfig

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition


@click.command("package")
@click.argument("app_path", type=click.Path(exists=True))
@click.option("--against", default="latest", help="Hop3 version to test against")
@click.option("--os", "target_os", help="Target OS (debian-12, ubuntu-24.04)")
@click.option("--with-service", multiple=True, help="Additional services")
@click.option("-v", "--verbose", is_flag=True)
@click.pass_context
def package(
    ctx: click.Context,
    app_path: str,
    against: str,
    target_os: str | None,
    with_service: tuple[str, ...],
    verbose: bool,
) -> None:
    """Validate a package against stable Hop3.

    This command allows package authors to test their application
    against a stable Hop3 release before publishing.
    """
    app_path_obj = Path(app_path)

    # Generate test definition from app
    test_def = generate_test_definition_from_app(app_path_obj)

    click.echo(f"Validating package: {test_def.name}")
    click.echo(f"Against Hop3: {against}")

    # Create target (pre-built image mode)
    docker_config = DockerConfig(
        image="hop3-ready:latest",
        container_name="hop3-package-test",
    )
    target = DockerTarget(docker_config)

    try:
        click.echo("\nStarting test environment...")
        target.start()

        # Run test
        runner = DeploymentTestRunner(
            target,
            cleanup=True,
            verbose=verbose or ctx.obj["verbose"],
        )

        result = runner.run(test_def)

        # Report result
        reporter = ConsoleReporter(verbose=verbose or ctx.obj["verbose"])
        reporter.report_package_result(result)

        sys.exit(0 if result.passed else 1)

    finally:
        target.stop()


@click.command("system")
@click.argument("app_names", nargs=-1)
# Target type (must specify one)
@click.option(
    "--docker", "target_type", flag_value="docker", help="Test using Docker container"
)
@click.option(
    "--ssh", "target_type", flag_value="remote", help="Test using SSH to remote host"
)
# Deployment source
@click.option(
    "--deploy-from",
    type=click.Choice(["local", "git", "pypi", "none"]),
    default="local",
    help="Deploy from: local code (default), git branch, pypi, or none (reuse existing)",
)
@click.option(
    "--reuse",
    is_flag=True,
    help="Reuse existing deployment (alias for --deploy-from none)",
)
@click.option("--branch", default="devel", help="Git branch (if --deploy-from git)")
@click.option("--clean", is_flag=True, help="Clean install (remove existing)")
# Connection options
@click.option("--host", help="Remote host (for --ssh, or remote Docker)")
@click.option("--port", type=int, default=22, help="SSH port")
@click.option("--user", default="root", help="SSH user")
@click.option("--ssh-key", help="SSH key path")
# Test options
@click.option(
    "--mode",
    type=click.Choice(["dev", "ci"]),
    default="dev",
    help="Test mode: dev (fast P0 only) or ci (fast+medium P0)",
)
@click.option("--keep", is_flag=True, help="Keep target after tests")
@click.option("-x", "--fail-fast", is_flag=True, help="Stop on first failure")
@click.option(
    "--report",
    type=click.Choice(["none", "text", "html"]),
    default="text",
    help="Report format: none, text (console), or html",
)
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode (suppress recap)")
@click.option("--debug", is_flag=True, help="Show detailed debug info on failure")
@click.option(
    "--logs-dir",
    type=click.Path(),
    help="Directory to save per-app log files",
)
@click.option(
    "--with",
    "features",
    multiple=True,
    help="Optional features to install (e.g., nix, mysql, redis)",
)
@click.pass_context
def system_test(  # noqa: C901, PLR0912, PLR0915
    ctx: click.Context,
    app_names: tuple[str, ...],
    target_type: str | None,
    deploy_from: str,
    reuse: bool,
    branch: str,
    clean: bool,
    host: str | None,
    port: int,
    user: str,
    ssh_key: str | None,
    mode: str,
    keep: bool,
    fail_fast: bool,
    report: str,
    quiet: bool,
    debug: bool,
    logs_dir: str | None,
    features: tuple[str, ...],
) -> None:
    """Test Hop3 system using real hop3-deploy.

    Deploys Hop3 via hop3-deploy, then runs tests against it.
    Optionally pass app names, paths, or scan directories.

    \b
    Examples:
      hop3-test system --docker              # Deploy + test all
      hop3-test system --docker --clean      # Clean install
      hop3-test system --docker --with all   # All features
      hop3-test system --ssh --host X        # Remote via SSH
      hop3-test system --ssh demos/demo03 apps/test-apps/010-flask-pip-wsgi
      hop3-test system --docker apps/docker-apps  # Scan a directory
    """
    verbose = ctx.obj["verbose"]

    # Require explicit target type
    if not target_type:
        click.echo("Error: Must specify --docker or --ssh", err=True)
        click.echo("\nExamples:")
        click.echo("  hop3-test system --docker")
        click.echo("  hop3-test system --ssh --host server.com")
        sys.exit(1)

    assert target_type is not None  # Type narrowing after sys.exit

    # Handle --reuse as alias for --deploy-from none
    if reuse:
        deploy_from = "none"

    # For SSH, get host from env if not provided
    if target_type == "remote" and not host:
        host = os.environ.get("HOP3_TEST_HOST")
        if not host:
            click.echo(
                "Error: --host required for --ssh (or set HOP3_TEST_HOST)", err=True
            )
            sys.exit(1)

    # Load catalog and select tests
    root = ctx.obj["root"]
    mode_config = get_mode_config(mode)

    tests: list[TestDefinition] = []
    if app_names:
        # Args serve double duty: directories to scan, or specific app paths
        scan_paths: list[str] = []
        direct_apps: list[str] = []
        for name in app_names:
            path = Path(name)
            if path.is_dir() and not (path / "hop3.toml").exists():
                # It's a directory to scan (e.g., apps/docker-apps)
                scan_paths.append(name)
            else:
                # It's a specific app path or name
                direct_apps.append(name)

        if scan_paths:
            catalog = Catalog(root)
            catalog.scan(paths=scan_paths)
            tests.extend(catalog.filter())

        if direct_apps:
            # Need catalog for name-based lookups
            if not scan_paths:
                # Build scan paths from direct app parents
                catalog = Catalog(root)
                parent_paths = list({
                    str(Path(a).parent) for a in direct_apps if "/" in a
                })
                if parent_paths:
                    catalog.scan(paths=parent_paths)

            for name in direct_apps:
                test, error = _lookup_test_by_name_or_path(name, catalog)
                if test:
                    tests.append(test)
                elif error:
                    click.echo(f"Warning: {error}", err=True)
    else:
        # No args - scan default directories and use mode-based selection
        default_paths = _get_default_scan_paths(root)
        catalog = Catalog(root)
        catalog.scan(paths=default_paths)

        selector = Selector(catalog)
        tests = selector.select_for_target(mode_config, target_type)

    if not tests:
        click.echo("No tests found")
        if app_names:
            click.echo(f"Apps searched: {', '.join(app_names)}")
        return

    # Show test list BEFORE deployment (immediate feedback)
    click.echo(f"\n{'=' * 70}")
    click.echo("SYSTEM TESTING MODE")
    click.echo("Testing Hop3 itself with known-good applications")
    click.echo(f"{'=' * 70}")
    click.echo(f"\nTarget: {target_type}")
    if host:
        click.echo(f"Host: {host}")
    click.echo(f"Deploy from: {deploy_from}")
    if deploy_from == "git":
        click.echo(f"Branch: {branch}")
    click.echo(f"Test mode: {mode} ({mode_config.description})")
    click.echo(f"Clean install: {clean}")
    click.echo(f"Features: {', '.join(features) if features else '(default)'}")
    click.echo(f"\nTests to run ({len(tests)}):")
    for t in tests:
        click.echo(f"  - {t.name}")
    click.echo("")  # Blank line before deployment starts

    # Build deployment config (None if reusing existing)
    deployment: DeploymentConfig | None = None
    if deploy_from != "none":
        # Pass features through as-is - "all" is expanded by the installer
        deployment = DeploymentConfig(
            source=cast("Literal['local', 'git', 'pypi']", deploy_from),
            branch=branch,
            clean=clean,
            verbose=verbose,
            features=list(features),  # Convert tuple to list
        )

    # Create target based on target type
    target_obj: DockerTarget | RemoteTarget
    if target_type == "docker":
        docker_config = DockerConfig(
            container_name="hop3-system-test",
            reuse_container=deploy_from == "none",
        )
        target_obj = DockerTarget(docker_config, deployment=deployment)
    else:
        # SSH target
        assert host is not None  # Validated above
        remote_config = RemoteConfig(
            host=host,
            port=port,
            user=user,
            ssh_key=ssh_key,
        )
        target_obj = RemoteTarget(remote_config, deployment=deployment)

    # Run tests
    run_system_tests(
        ctx, tests, target_obj, keep, fail_fast, report, quiet, debug, logs_dir
    )


def _get_default_scan_paths(root: Path) -> list[str]:
    """Get default scan paths for the 'run everything' case.

    Scans all subdirectories of apps/ that exist, plus demos/.
    """
    paths: list[str] = []
    apps_dir = root / "apps"
    if apps_dir.is_dir():
        for child in sorted(apps_dir.iterdir()):
            if child.is_dir():
                paths.append(str(child.relative_to(root)))
    demos_dir = root / "demos"
    if demos_dir.is_dir():
        paths.append("demos")
    return paths


def _load_test_from_path(path_str: str) -> tuple[TestDefinition | None, str | None]:
    """Load a test directly from a path without catalog lookup.

    Args:
        path_str: Path to the test directory

    Returns:
        Tuple of (test_definition, error_message). One will be None.
    """
    path = Path(path_str.rstrip("/"))

    if not path.is_dir():
        return None, f"Not a directory: {path}"

    # Check for hop3.toml or test.toml
    if not (path / "hop3.toml").exists() and not (path / "test.toml").exists():
        # Check if it looks like a legacy app
        if not (path / "Procfile").exists() and not (path / "index.html").exists():
            return None, f"No hop3.toml, test.toml, or Procfile found in {path}"

    try:
        test = load_test_definition_smart(path)
        return test, None
    except Exception as e:
        return None, f"Failed to load {path}: {e}"


def _all_args_are_paths(app_names: tuple[str, ...]) -> bool:
    """Check if all arguments look like paths (contain / or are directories)."""
    if not app_names:
        return False
    return all("/" in name or Path(name).is_dir() for name in app_names)


def _select_tests_for_apps(  # noqa: C901, PLR0912
    app_names: tuple[str, ...],
    root: Path,
) -> list[TestDefinition]:
    """Select tests based on app names or paths.

    Bypasses catalog scan when all arguments are paths for efficiency.
    """
    tests: list[TestDefinition] = []

    if app_names and _all_args_are_paths(app_names):
        # Direct path loading - no catalog scan needed
        for path_str in app_names:
            test, error = _load_test_from_path(path_str)
            if test:
                tests.append(test)
            elif error:
                click.echo(f"Warning: {error}", err=True)
    elif app_names:
        # Need catalog for name-based lookup
        scan_paths: list[str] = []
        for name in app_names:
            path = Path(name)
            if path.is_dir() and not (path / "hop3.toml").exists():
                scan_paths.append(name)
            elif "/" in name:
                parent = str(Path(name).parent)
                if parent not in scan_paths:
                    scan_paths.append(parent)

        catalog = Catalog(root)
        if scan_paths:
            catalog.scan(paths=scan_paths)
        else:
            # Fall back to default scan paths
            catalog.scan(paths=_get_default_scan_paths(root))

        for name in app_names:
            test, error = _lookup_test_by_name_or_path(name, catalog)
            if test:
                tests.append(test)
            elif error:
                click.echo(f"Warning: {error}", err=True)
    else:
        # No args - scan default paths and get all tests
        catalog = Catalog(root)
        catalog.scan(paths=_get_default_scan_paths(root))
        tests = catalog.filter()

    return tests


def _create_app_test_target(
    target: str,
    image: str,
    host: str | None,
    port: int,
    user: str,
    ssh_key: str | None,
) -> DockerTarget | RemoteTarget:
    """Create target for app testing."""
    if target in {"ready", "docker"}:
        docker_config = DockerConfig(
            image=image if target == "ready" else "hop3-ready:latest",
            container_name="hop3-app-test",
        )
        return DockerTarget(docker_config)

    # Remote target
    if not host:
        click.echo("--host required for remote target", err=True)
        sys.exit(1)
    assert host is not None
    remote_config = RemoteConfig(
        host=host,
        port=port,
        user=user,
        ssh_key=ssh_key,
    )
    return RemoteTarget(remote_config)


def _lookup_test_by_name_or_path(name: str, catalog: Catalog) -> tuple:
    """Look up a test by name or path.

    Returns:
        Tuple of (test_definition, error_message). One will be None.
    """
    test: TestDefinition | None = None

    # Check if it looks like a path (contains / or is a valid directory)
    if "/" in name or Path(name).is_dir():
        path = Path(name.rstrip("/"))
        test = catalog.get_test_by_path(path)

        # If path lookup failed but it's a valid directory,
        # try to load it directly using smart loading (hop3.toml + test.toml)
        if test is None and path.is_dir():
            # Try smart loading which handles hop3.toml, test.toml, or auto-generation
            if (path / "hop3.toml").exists() or (path / "test.toml").exists():
                try:
                    test = load_test_definition_smart(path)
                except Exception as e:
                    return None, f"Failed to load {path}: {e}"

    # Fall back to name-based lookup
    if test is None:
        test = catalog.get_test(name)
        # Also try just the directory name if full path was given
        if test is None and "/" in name:
            dir_name = Path(name).name
            test = catalog.get_test(dir_name)

    if test is None:
        return None, f"Test not found: {name}"

    return test, None


@click.command("apps")
@click.argument("app_names", nargs=-1)
@click.option(
    "--target",
    type=click.Choice(["ready", "docker", "remote"]),
    default="ready",
    help="Target: ready (pre-built image), docker (legacy), remote (SSH)",
)
@click.option(
    "--image", default="hop3-ready:latest", help="Docker image for ready target"
)
@click.option("--host", help="Remote host (for remote target)")
@click.option("--port", type=int, default=22, help="SSH port (for remote target)")
@click.option("--user", default="root", help="SSH user (for remote target)")
@click.option("--ssh-key", help="SSH key path (for remote target)")
@click.option("--keep", is_flag=True, help="Keep apps deployed after testing")
@click.option("-x", "--fail-fast", is_flag=True, help="Stop on first failure")
@click.option(
    "--report",
    type=click.Choice(["none", "text", "html"]),
    default="text",
    help="Report format: none, text (console), or html",
)
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode (suppress recap)")
@click.option("--debug", is_flag=True, help="Show detailed debug info on failure")
@click.option(
    "--logs-dir",
    type=click.Path(),
    help="Directory to save per-app log files",
)
@click.pass_context
def apps_test(
    ctx: click.Context,
    app_names: tuple[str, ...],
    target: str,
    image: str,
    host: str | None,
    port: int,
    user: str,
    ssh_key: str | None,
    keep: bool,
    fail_fast: bool,
    report: str,
    quiet: bool,
    debug: bool,
    logs_dir: str | None,
) -> None:
    """Test applications against a pre-deployed Hop3 server.

    This command uses a pre-built Docker image or existing server to test
    applications. No Hop3 deployment is performed - the server is assumed
    to be already working.

    This is for:
    - Testing apps (the focus is the app, not Hop3)
    - Fast iteration (skip 5+ minute installation)
    - Package validation before publishing

    Examples:
        hop3-test apps                      # Test all apps against ready image
        hop3-test apps 010-flask            # Test specific app
        hop3-test apps apps/docker-apps/*   # Test specific paths (no catalog scan)
        hop3-test apps apps/docker-apps     # Scan a directory
        hop3-test apps --target remote --host X  # Against remote server
    """
    # Select tests - bypass catalog scan when all args are paths
    tests = _select_tests_for_apps(app_names, ctx.obj["root"])

    if not tests:
        click.echo("No tests found")
        return

    click.echo(f"\n{'=' * 70}")
    click.echo("APP TESTING MODE")
    click.echo("Testing applications against pre-deployed Hop3")
    click.echo(f"{'=' * 70}")
    click.echo(f"\nTarget: {target}")
    if target == "ready":
        click.echo(f"Image: {image}")
    click.echo(f"Tests to run: {len(tests)}")

    # Create target and run tests
    target_obj = _create_app_test_target(target, image, host, port, user, ssh_key)
    run_app_tests(
        ctx, tests, target_obj, keep, fail_fast, report, quiet, debug, logs_dir
    )
