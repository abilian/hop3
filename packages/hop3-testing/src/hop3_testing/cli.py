# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""New CLI for hop3-test with test.toml support.

This module provides the new CLI commands:
- hop3-test list: List available tests
- hop3-test show: Show test details
- hop3-test dev: Run developer tests
- hop3-test ci: Run CI tests
- hop3-test package: Validate a package

The original functionality is preserved and can be accessed via:
- hop3-test run: Run tests (original behavior)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from .catalog import TestCatalog
from .catalog.models import Category
from .results import ConsoleReporter, ResultStore
from .runners import DemoTestRunner, DeploymentTestRunner, TutorialTestRunner
from .selector import TestSelector, get_mode_config
from .targets import DockerDeployTarget, DockerTarget, ReadyTarget, RemoteTarget

if TYPE_CHECKING:
    from .catalog.models import TestDefinition
    from .runners.base import TestResult
    from .targets.base import DeploymentTarget


@click.group(invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Hop3 Test Runner - Unified testing for Hop3.

    Run deployment tests, demos, and tutorials against Hop3 targets.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["root"] = Path.cwd()

    # If no subcommand, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command("list")
@click.option(
    "--category", "-c", help="Filter by category (deployment, demo, tutorial)"
)
@click.option("--tier", "-t", help="Filter by tier (fast, medium, slow, very-slow)")
@click.option("--priority", "-p", help="Filter by priority (P0, P1, P2)")
@click.option("--tag", multiple=True, help="Filter by tag")
@click.option(
    "--format", "output_format", type=click.Choice(["table", "json"]), default="table"
)
@click.pass_context
def list_tests(
    ctx: click.Context,
    category: str | None,
    tier: str | None,
    priority: str | None,
    tag: tuple[str, ...],
    output_format: str,
) -> None:
    """List available tests."""
    catalog = TestCatalog(ctx.obj["root"])
    catalog.scan()

    tests = catalog.filter(
        categories=[category] if category else None,
        tiers=[tier] if tier else None,
        priorities=[priority] if priority else None,
        tags=list(tag) if tag else None,
    )

    if output_format == "json":
        import json

        output = [
            {
                "name": t.name,
                "category": t.category.value,
                "tier": t.tier.value,
                "priority": t.priority.value,
                "description": t.description,
            }
            for t in tests
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        # Table output
        click.echo(f"{'Name':<40} {'Category':<12} {'Tier':<10} {'Priority':<8}")
        click.echo("-" * 72)
        for t in tests:
            click.echo(
                f"{t.name:<40} {t.category.value:<12} {t.tier.value:<10} {t.priority.value:<8}"
            )
        click.echo(f"\nTotal: {len(tests)} tests")


@cli.command("show")
@click.argument("test_name")
@click.pass_context
def show_test(ctx: click.Context, test_name: str) -> None:
    """Show details of a specific test."""
    catalog = TestCatalog(ctx.obj["root"])
    catalog.scan()

    test = catalog.get_test(test_name)
    if not test:
        click.echo(f"Test not found: {test_name}", err=True)
        sys.exit(1)

    click.echo(f"Name: {test.name}")
    click.echo(f"Category: {test.category.value}")
    click.echo(f"Tier: {test.tier.value}")
    click.echo(f"Priority: {test.priority.value}")
    if test.description:
        click.echo(f"Description: {test.description}")
    click.echo(f"Source: {test.source_path}")
    click.echo(f"Targets: {', '.join(t.value for t in test.requirements.targets)}")
    if test.requirements.services:
        click.echo(f"Services: {', '.join(test.requirements.services)}")
    if test.metadata.covers:
        click.echo(f"Tags: {', '.join(test.metadata.covers)}")
    click.echo(f"Validations: {len(test.validations)}")


@cli.command("dev")
@click.option("--target", type=click.Choice(["docker", "remote"]), default="docker")
@click.option("--host", help="Remote host (for remote target)")
@click.option("--keep", is_flag=True, help="Keep target after tests")
@click.option("--keep-apps", is_flag=True, help="Keep apps deployed after testing")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.pass_context
def dev(
    ctx: click.Context,
    target: str,
    host: str | None,
    keep: bool,
    keep_apps: bool,
    fail_fast: bool,
) -> None:
    """Run developer tests (fast, P0 only).

    This runs fast P0 deployment tests in Docker. Use this for quick
    validation during development.
    """
    _run_tests(
        ctx,
        mode="dev",
        target_type=target,
        host=host,
        keep_target=keep,
        keep_apps=keep_apps,
        fail_fast=fail_fast,
    )


@cli.command("ci")
@click.option("--target", type=click.Choice(["docker", "remote"]), default="docker")
@click.option("--host", help="Remote host (for remote target)")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.pass_context
def ci(
    ctx: click.Context,
    target: str,
    host: str | None,
    fail_fast: bool,
) -> None:
    """Run CI tests (fast+medium, P0).

    This runs fast and medium P0 tests suitable for CI pipelines.
    """
    _run_tests(
        ctx,
        mode="ci",
        target_type=target,
        host=host,
        keep_target=False,
        keep_apps=False,
        fail_fast=fail_fast,
    )


@cli.command("nightly")
@click.option("--target", type=click.Choice(["docker", "remote"]), default="docker")
@click.option("--host", help="Remote host (for remote target)")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.pass_context
def nightly(
    ctx: click.Context,
    target: str,
    host: str | None,
    fail_fast: bool,
) -> None:
    """Run nightly tests (all tiers, all priorities).

    This runs all deployment tests, demos, and tutorials. Intended for
    nightly CI builds with more time.
    """
    _run_tests(
        ctx,
        mode="nightly",
        target_type=target,
        host=host,
        keep_target=False,
        keep_apps=False,
        fail_fast=fail_fast,
    )


@cli.command("run")
@click.argument("apps", nargs=-1)
@click.option("--target", type=click.Choice(["docker", "remote"]), default="docker")
@click.option("--host", help="Remote host (for remote target)")
@click.option("--port", type=int, default=22, help="SSH port (for remote target)")
@click.option("--user", default="hop3", help="SSH user (for remote target)")
@click.option("--ssh-key", help="SSH key path (for remote target)")
@click.option("--category", "-c", help="Filter by category")
@click.option("--keep", is_flag=True, help="Keep apps deployed after testing")
@click.option("--keep-target", is_flag=True, help="Keep target running after tests")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.option("--debug", is_flag=True, help="Debug mode")
@click.option("--use-cache", is_flag=True, help="Skip Docker build if image exists")
@click.option(
    "--force-rebuild", is_flag=True, help="Force full rebuild without Docker cache"
)
@click.pass_context
def run_command(
    ctx: click.Context,
    apps: tuple[str, ...],
    target: str,
    host: str | None,
    port: int,
    user: str,
    ssh_key: str | None,
    category: str | None,
    keep: bool,
    keep_target: bool,
    fail_fast: bool,
    debug: bool,
    use_cache: bool,
    force_rebuild: bool,
) -> None:
    """Run tests (backwards compatible with original hop3-test).

    This command provides the same interface as the original hop3-test CLI.
    You can specify apps by name or path, or use --category to filter.

    Examples:
        hop3-test-new run --target docker
        hop3-test-new run 010-flask-pip-wsgi 020-nodejs-express
        hop3-test-new run --category python-simple
    """
    verbose = ctx.obj["verbose"]

    # Load catalog
    catalog = TestCatalog(ctx.obj["root"])
    catalog.scan()

    # Select tests based on arguments
    if apps:
        # Filter by specific app names
        tests = []
        for app_name in apps:
            test = catalog.get_test(app_name)
            if test:
                tests.append(test)
            else:
                # Try as a path
                app_path = Path(app_name)
                if app_path.exists():
                    from .catalog.loader import generate_test_definition_from_app

                    tests.append(generate_test_definition_from_app(app_path))
                else:
                    click.echo(f"Warning: Test not found: {app_name}", err=True)
    elif category:
        tests = catalog.filter(categories=[category])
    else:
        tests = list(catalog.all_tests())

    if not tests:
        click.echo("No tests found to run")
        sys.exit(1)

    click.echo(f"\nFound {len(tests)} test(s) to run")
    for t in tests:
        click.echo(f"  - {t.name} ({t.category.value})")

    # Create target
    target_obj = _create_target_with_options(
        target_type=target,
        host=host,
        port=port,
        user=user,
        ssh_key=ssh_key,
        use_cache=use_cache,
        force_rebuild=force_rebuild,
    )

    # Initialize result storage
    store = ResultStore()
    reporter = ConsoleReporter(verbose=verbose)

    try:
        click.echo("\nStarting deployment target...")
        target_obj.start()

        store.start_run(
            mode="run",
            target_type=target,
            target_name=target_obj.info.ssh_host,
        )

        # Run tests
        results = []
        for test in tests:
            click.echo(f"\n{'=' * 70}")
            click.echo(f"Testing: {test.name}")
            click.echo(f"Category: {test.category.value}")
            if test.description:
                click.echo(f"Description: {test.description}")
            click.echo(f"{'=' * 70}\n")

            result = _run_test(
                test, target_obj, cleanup=not keep, verbose=verbose or debug
            )
            results.append(result)
            store.save(result)

            if result.passed:
                click.echo(f"\n✓ {test.name} PASSED")
            else:
                click.echo(f"\n❌ {test.name} FAILED")
                if result.error:
                    click.echo(f"  Error: {result.error}")

            if fail_fast and not result.passed:
                click.echo("\nFail fast enabled, stopping tests")
                break

        # Summary
        store.finish_run()
        reporter.summary(results)

        # Exit code
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        sys.exit(0 if failed == 0 else 1)

    finally:
        if not keep_target:
            click.echo("\nStopping target...")
            target_obj.stop()


@cli.command("package")
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
    from .catalog.loader import generate_test_definition_from_app

    app_path_obj = Path(app_path)

    # Generate test definition from app
    test_def = generate_test_definition_from_app(app_path_obj)

    click.echo(f"Validating package: {test_def.name}")
    click.echo(f"Against Hop3: {against}")

    # Create target
    target = DockerTarget({"force_rebuild": False})

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


# =============================================================================
# NEW COMMANDS: system and apps (using hop3-deploy infrastructure)
# =============================================================================


@cli.command("system")
@click.option(
    "--deploy-from",
    type=click.Choice(["local", "git", "none"]),
    default="local",
    help="Deploy Hop3 from: local code, git branch, or skip deployment",
)
@click.option("--branch", default="devel", help="Git branch (if --deploy-from git)")
@click.option("--clean", is_flag=True, help="Clean install (remove existing)")
@click.option("--target", type=click.Choice(["docker", "remote"]), default="docker")
@click.option("--host", help="Remote host (for remote target)")
@click.option(
    "--mode",
    type=click.Choice(["dev", "ci"]),
    default="dev",
    help="Test mode: dev (fast P0 only) or ci (fast+medium P0)",
)
@click.option("--keep", is_flag=True, help="Keep target after tests")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.option(
    "--report",
    type=click.Choice(["none", "text", "html"]),
    default="text",
    help="Report format: none, text (console), or html",
)
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode (suppress recap)")
@click.pass_context
def system_test(
    ctx: click.Context,
    deploy_from: str,
    branch: str,
    clean: bool,
    target: str,
    host: str | None,
    mode: str,
    keep: bool,
    fail_fast: bool,
    report: str,
    quiet: bool,
) -> None:
    """Test Hop3 system using real hop3-deploy.

    This command deploys Hop3 using the actual hop3-deploy infrastructure,
    then runs tests against it. This ensures tests exercise the real
    installation and deployment paths.

    Examples:
        hop3-test-new system                    # Deploy local code to Docker (dev mode)
        hop3-test-new system --mode ci          # Include medium-tier tests
        hop3-test-new system --deploy-from git  # Deploy from git
        hop3-test-new system --clean            # Clean install
        hop3-test-new system --deploy-from none # Use existing deployment
    """
    verbose = ctx.obj["verbose"]

    # Load catalog and select tests based on mode
    catalog = TestCatalog(ctx.obj["root"])
    catalog.scan()

    mode_config = get_mode_config(mode)
    selector = TestSelector(catalog)
    tests = selector.select_for_target(mode_config, target)

    if not tests:
        click.echo("No tests found")
        return

    click.echo(f"\n{'=' * 70}")
    click.echo("SYSTEM TESTING MODE")
    click.echo("Testing Hop3 itself with known-good applications")
    click.echo(f"{'=' * 70}")
    click.echo(f"\nDeploy from: {deploy_from}")
    if deploy_from == "git":
        click.echo(f"Branch: {branch}")
    click.echo(f"Test mode: {mode} ({mode_config.description})")
    click.echo(f"Clean install: {clean}")
    click.echo(f"Tests to run: {len(tests)}")

    # Create target using new hop3-deploy based targets
    if target == "docker":
        target_obj = DockerDeployTarget({
            "local": deploy_from == "local",
            "clean": clean,
            "branch": branch,
            "verbose": verbose,
        })
    else:
        # Remote target (not yet implemented with hop3-deploy wrapper)
        if not host:
            click.echo("--host required for remote target", err=True)
            sys.exit(1)
        # Fall back to legacy RemoteTarget for now
        target_obj = RemoteTarget({"host": host})

    # Run tests
    _run_system_tests(ctx, tests, target_obj, keep, fail_fast, report, quiet)


@cli.command("apps")
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
@click.option("--category", "-c", help="Filter by category")
@click.option("--keep", is_flag=True, help="Keep apps deployed after testing")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.option(
    "--report",
    type=click.Choice(["none", "text", "html"]),
    default="text",
    help="Report format: none, text (console), or html",
)
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode (suppress recap)")
@click.pass_context
def apps_test(
    ctx: click.Context,
    app_names: tuple[str, ...],
    target: str,
    image: str,
    host: str | None,
    category: str | None,
    keep: bool,
    fail_fast: bool,
    report: str,
    quiet: bool,
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
        hop3-test-new apps                      # Test all apps against ready image
        hop3-test-new apps 010-flask            # Test specific app
        hop3-test-new apps --category python    # Test by category
        hop3-test-new apps --target remote --host X  # Against remote server
    """
    verbose = ctx.obj["verbose"]

    # Load catalog
    catalog = TestCatalog(ctx.obj["root"])
    catalog.scan()

    # Select tests
    if app_names:
        tests = []
        for name in app_names:
            test = catalog.get_test(name)
            if test:
                tests.append(test)
            else:
                click.echo(f"Warning: Test not found: {name}", err=True)
    elif category:
        tests = catalog.filter(categories=[category])
    else:
        # All deployment tests (not demos/tutorials)
        tests = catalog.filter(categories=["deployment"])

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

    # Create target
    if target == "ready":
        target_obj = ReadyTarget({"image": image, "verbose": verbose})
    elif target == "docker":
        # Legacy Docker target (will be deprecated)
        target_obj = DockerTarget({"force_rebuild": False})
    else:
        if not host:
            click.echo("--host required for remote target", err=True)
            sys.exit(1)
        target_obj = RemoteTarget({"host": host})

    # Run tests
    _run_app_tests(ctx, tests, target_obj, keep, fail_fast, report, quiet)


def _run_system_tests(
    ctx: click.Context,
    tests: list,
    target: DeploymentTarget,
    keep: bool,
    fail_fast: bool,
    report: str = "text",
    quiet: bool = False,
) -> None:
    """Run system tests with full deployment."""
    verbose = ctx.obj["verbose"]
    store = ResultStore()
    reporter = ConsoleReporter(verbose=verbose, quiet=quiet)

    try:
        click.echo("\nDeploying Hop3 via hop3-deploy...")
        target.start()

        store.start_run(
            mode="system",
            target_type="docker-deploy",
            target_name=target.info.ssh_host,
        )

        results = []
        for test in tests:
            click.echo(f"\n[{test.name}] ", nl=False)

            result = _run_test(test, target, cleanup=True, verbose=verbose)
            results.append(result)
            store.save(result)

            reporter.report_test(result)

            if fail_fast and not result.passed:
                click.echo("\nFail fast enabled, stopping tests")
                break

        store.finish_run()
        reporter.summary(results)

        # Generate reports based on --report option
        _generate_reports(target, report, results)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        sys.exit(0 if failed == 0 else 1)

    finally:
        if not keep:
            click.echo("\nStopping target...")
            target.stop()


def _run_app_tests(
    ctx: click.Context,
    tests: list,
    target: DeploymentTarget,
    keep: bool,
    fail_fast: bool,
    report: str = "text",
    quiet: bool = False,
) -> None:
    """Run app tests against pre-deployed server."""
    verbose = ctx.obj["verbose"]
    store = ResultStore()
    reporter = ConsoleReporter(verbose=verbose, quiet=quiet)

    try:
        click.echo("\nStarting test environment...")
        target.start()
    except RuntimeError as e:
        # Clean exit for expected errors (e.g., image not found)
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)

    try:
        store.start_run(
            mode="apps",
            target_type="ready",
            target_name=target.info.ssh_host,
        )

        results = []
        for test in tests:
            click.echo(f"\n[{test.name}] ", nl=False)

            result = _run_test(test, target, cleanup=not keep, verbose=verbose)
            results.append(result)
            store.save(result)

            reporter.report_test(result)

            if fail_fast and not result.passed:
                click.echo("\nFail fast enabled, stopping tests")
                break

        store.finish_run()
        reporter.summary(results)

        # Generate reports based on --report option
        _generate_reports(target, report, results)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        sys.exit(0 if failed == 0 else 1)

    finally:
        click.echo("\nStopping target...")
        target.stop()


def _run_tests(
    ctx: click.Context,
    mode: str,
    target_type: str,
    host: str | None,
    keep_target: bool,
    keep_apps: bool,
    fail_fast: bool,
) -> None:
    """Common test execution logic."""
    verbose = ctx.obj["verbose"]

    # Load catalog
    catalog = TestCatalog(ctx.obj["root"])
    catalog.scan()

    # Get mode config and select tests
    mode_config = get_mode_config(mode)
    selector = TestSelector(catalog)
    tests = selector.select_for_target(mode_config, target_type)

    if not tests:
        click.echo("No tests to run")
        return

    click.echo(f"Running {len(tests)} tests in {mode} mode")

    # Create target
    target = _create_target(target_type, host)

    # Initialize result storage
    store = ResultStore()
    reporter = ConsoleReporter(verbose=verbose)

    try:
        click.echo("\nStarting test environment...")
        target.start()

        store.start_run(
            mode=mode,
            target_type=target_type,
            target_name=target.info.ssh_host,
        )

        # Run tests
        results = []
        for test in tests:
            click.echo(f"\n[{test.name}] ", nl=False)

            result = _run_test(test, target, cleanup=not keep_apps, verbose=verbose)
            results.append(result)
            store.save(result)

            reporter.report_test(result)

            if fail_fast and not result.passed:
                click.echo("\nFail fast enabled, stopping tests")
                break

        # Summary
        store.finish_run()
        reporter.summary(results)

        # Exit code
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        sys.exit(0 if failed == 0 else 1)

    finally:
        if not keep_target:
            click.echo("\nStopping test environment...")
            target.stop()


def _run_test(
    test: TestDefinition,
    target: DeploymentTarget,
    cleanup: bool,
    verbose: bool,
) -> TestResult:
    """Run a single test with the appropriate runner."""
    if test.category == Category.DEMO:
        runner = DemoTestRunner(target, cleanup=cleanup, verbose=verbose)
    elif test.category == Category.TUTORIAL:
        runner = TutorialTestRunner(target, cleanup=cleanup, verbose=verbose)
    else:
        # Default to deployment runner for deployment category and any others
        runner = DeploymentTestRunner(target, cleanup=cleanup, verbose=verbose)

    return runner.run(test)


def _generate_reports(
    target: DeploymentTarget,
    report: str,
    results: list,
) -> None:
    """Generate diagnostic reports based on report option.

    Args:
        target: The deployment target (may have diagnostics)
        report: Report format: "none", "text", or "html"
        results: List of test results
    """
    if report == "none":
        return

    # Check if target has diagnostics (new targets do)
    if hasattr(target, "diagnostics") and hasattr(target, "save_diagnostics"):
        if report == "html":
            log_path = target.save_diagnostics(generate_html=True)
            click.echo(f"\nDiagnostic logs saved to: {log_path}")
        elif report == "text":
            # Text report - save logs and show console output if there were failures
            has_failures = any(not r.passed for r in results)
            if has_failures:
                log_path = target.save_diagnostics(generate_html=False)
                click.echo(f"\nDiagnostic logs saved to: {log_path}")
                # Show diagnostics in console
                if hasattr(target.diagnostics, "dump_to_console"):
                    click.echo(target.diagnostics.dump_to_console())


def _create_target(target_type: str, host: str | None) -> DeploymentTarget:
    """Create a deployment target (simple version)."""
    return _create_target_with_options(target_type=target_type, host=host)


@cli.command("build-ready-image")
@click.option("--tag", default="hop3-ready:latest", help="Image tag")
@click.option("--no-cache", is_flag=True, help="Build without Docker cache")
@click.pass_context
def build_ready_image(ctx: click.Context, tag: str, no_cache: bool) -> None:
    """Build the hop3-ready Docker image for app testing.

    This builds a Docker image with Hop3 pre-installed and ready to use.
    The image is used by 'hop3-test apps' for fast app testing.

    Examples:
        hop3-test-new build-ready-image                    # Build default image
        hop3-test-new build-ready-image --tag my-hop3:v1   # Custom tag
        hop3-test-new build-ready-image --no-cache         # Force rebuild
    """
    import subprocess

    # Find project root and Dockerfile
    root = ctx.obj["root"]
    dockerfile_path = root / "packages" / "hop3-server" / "tests" / "d_e2e" / "docker" / "Dockerfile"

    if not dockerfile_path.exists():
        click.echo(f"Dockerfile not found at: {dockerfile_path}", err=True)
        sys.exit(1)

    click.echo(f"\n{'=' * 70}")
    click.echo("Building hop3-ready Docker image")
    click.echo(f"{'=' * 70}")
    click.echo(f"\nDockerfile: {dockerfile_path}")
    click.echo(f"Context: {root}")
    click.echo(f"Tag: {tag}")
    click.echo()

    # Build command
    cmd = [
        "docker", "build",
        "-f", str(dockerfile_path),
        "-t", tag,
    ]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(str(root))

    click.echo(f"Running: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, check=True)
        click.echo(f"\n{'=' * 70}")
        click.echo(f"Successfully built: {tag}")
        click.echo(f"{'=' * 70}")
        click.echo("\nYou can now run:")
        click.echo(f"  hop3-test-new apps           # Test all apps")
        click.echo(f"  hop3-test-new apps 010-flask # Test specific app")
    except subprocess.CalledProcessError as e:
        click.echo(f"\nBuild failed with exit code {e.returncode}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo("Docker not found. Please install Docker.", err=True)
        sys.exit(1)


def _create_target_with_options(
    target_type: str,
    host: str | None = None,
    port: int = 22,
    user: str = "hop3",
    ssh_key: str | None = None,
    use_cache: bool = False,
    force_rebuild: bool = False,
) -> DeploymentTarget:
    """Create a deployment target with full options."""
    import os

    if target_type == "docker":
        return DockerTarget({
            "rebuild": not use_cache,
            "use_cache": use_cache,
            "force_rebuild": force_rebuild,
        })
    if target_type == "remote":
        # Get host from args or environment
        actual_host = host or os.getenv("HOP3_TEST_HOST")
        if not actual_host:
            click.echo(
                "--host required for remote target (or set HOP3_TEST_HOST)", err=True
            )
            sys.exit(1)

        return RemoteTarget({
            "host": actual_host,
            "port": port,
            "user": user,
            "ssh_key": ssh_key or os.getenv("HOP3_TEST_SSH_KEY"),
        })
    click.echo(f"Unknown target type: {target_type}", err=True)
    sys.exit(1)


def main() -> None:
    """Entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
