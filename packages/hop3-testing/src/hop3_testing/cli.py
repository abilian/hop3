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

import html
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import click

from .catalog import TestCatalog
from .catalog.loader import generate_test_definition_from_app
from .catalog.models import Category
from .results import ConsoleReporter, ResultStore
from .runners import DemoTestRunner, DeploymentTestRunner, TutorialTestRunner
from .selector import TestSelector, get_mode_config
from .targets import (
    DockerDeployTarget,
    DockerTarget,
    ReadyTarget,
    RemoteDeployTarget,
    RemoteTarget,
)

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
@click.option("--port", type=int, default=22, help="SSH port (for remote target)")
@click.option("--user", default="root", help="SSH user (for remote target)")
@click.option("--ssh-key", help="SSH key path (for remote target)")
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
    port: int,
    user: str,
    ssh_key: str | None,
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
        # Remote target
        if not host:
            click.echo("--host required for remote target", err=True)
            sys.exit(1)

        if deploy_from == "none":
            # Connect to existing Hop3 server (no deployment)
            target_config = {
                "host": host,
                "port": port,
                "user": user,
            }
            if ssh_key:
                target_config["ssh_key"] = ssh_key
            target_obj = RemoteTarget(target_config)
        else:
            # Deploy Hop3 to remote server first
            target_obj = RemoteDeployTarget({
                "host": host,
                "port": port,
                "user": user,
                "local": deploy_from == "local",
                "clean": clean,
                "branch": branch,
                "verbose": verbose,
            })

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
@click.option("--port", type=int, default=22, help="SSH port (for remote target)")
@click.option("--user", default="root", help="SSH user (for remote target)")
@click.option("--ssh-key", help="SSH key path (for remote target)")
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
    port: int,
    user: str,
    ssh_key: str | None,
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
        target_config = {
            "host": host,
            "port": port,
            "user": user,
        }
        if ssh_key:
            target_config["ssh_key"] = ssh_key
        target_obj = RemoteTarget(target_config)

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
            log_path = target.save_diagnostics(generate_html=False)
            # Generate comprehensive HTML report with test results
            html_path = _generate_html_report(target, results, log_path)
            click.echo(f"\nHTML report saved to: {html_path}")
            click.echo(f"Diagnostic logs saved to: {log_path}")
        elif report == "text":
            # Text report - save logs and show console output if there were failures
            has_failures = any(not r.passed for r in results)
            if has_failures:
                log_path = target.save_diagnostics(generate_html=False)
                click.echo(f"\nDiagnostic logs saved to: {log_path}")
                # Show diagnostics in console
                if hasattr(target.diagnostics, "dump_to_console"):
                    click.echo(target.diagnostics.dump_to_console())


def _generate_html_report(
    target: DeploymentTarget, results: list, log_path: Path
) -> Path:
    """Generate a comprehensive HTML report with test results and diagnostics.

    Args:
        target: The deployment target (has diagnostics)
        results: List of TestResult objects
        log_path: Path to diagnostic logs

    Returns:
        Path to generated HTML report
    """
    # Calculate summary stats
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    total_duration = sum(r.total_duration for r in results)

    def is_short_content(text: str) -> bool:
        """Check if content is short enough to show inline (no foldable section)."""
        return len(text) < 100 and "\n" not in text

    def phase_html(
        phase_id: str, status: str, name: str, content: str, is_success: bool
    ) -> str:
        """Generate HTML for a phase, using inline or foldable based on content length."""
        status_class = "phase-success" if is_success else "phase-failure"
        escaped_content = html.escape(content)

        if is_short_content(content):
            # Short content: show inline, no foldable
            return f"""
            <div class="phase {status_class} phase-inline">
                <span class="phase-icon">{status}</span>
                <span class="phase-name">{html.escape(name)}</span>
                <span class="phase-message">{escaped_content}</span>
            </div>
            """
        # Long content: foldable section
        return f"""
            <div class="phase {status_class}" onclick="togglePhase('{phase_id}')">
                <span class="phase-icon">{status}</span>
                <span class="phase-name">{html.escape(name)}</span>
                <span class="phase-toggle">+</span>
            </div>
            <div id="{phase_id}" class="phase-logs" style="display:none">
                <pre>{escaped_content}</pre>
            </div>
            """

    # Build test results - each test is a clickable card
    test_cards = []
    for idx, r in enumerate(results):
        status_class = "success" if r.passed else "failure"
        status_icon = "\u2713" if r.passed else "\u2717"
        test_id = f"test-{idx}"

        # Build phases list
        phases_html = []

        # Phase 1: Deployment (only if there are logs or it failed)
        if r.deploy_logs:
            deploy_status = (
                "\u2713" if not r.error or "deploy" not in r.error.lower() else "\u2717"
            )
            is_success = deploy_status == "\u2713"
            phases_html.append(
                phase_html(
                    f"{test_id}-deploy",
                    deploy_status,
                    "Deploy",
                    r.deploy_logs,
                    is_success,
                )
            )

        # Phase 2: Validations
        if r.validation_results:
            for v_idx, v in enumerate(r.validation_results):
                v_status = "\u2713" if v.passed else "\u2717"
                v_id = f"{test_id}-val-{v_idx}"

                # Build content from message and details
                v_content = v.message or f"{'Passed' if v.passed else 'Failed'}"
                if v.details:
                    # Add relevant details
                    detail_lines = []
                    for key, val in v.details.items():
                        if key not in {
                            "passed",
                        }:  # Skip redundant fields
                            detail_lines.append(f"{key}: {val}")
                    if detail_lines:
                        v_content += "\n" + "\n".join(detail_lines)

                phases_html.append(
                    phase_html(v_id, v_status, v.type_name, v_content, v.passed)
                )

        # Phase 3: Error (if any, always foldable since errors tend to be long)
        if r.error:
            phases_html.append(f"""
            <div class="phase phase-failure" onclick="togglePhase('{test_id}-error')">
                <span class="phase-icon">\u2717</span>
                <span class="phase-name">Error</span>
                <span class="phase-toggle">+</span>
            </div>
            <div id="{test_id}-error" class="phase-logs" style="display:none">
                <pre class="error-log">{html.escape(r.error)}</pre>
            </div>
            """)

        test_cards.append(f"""
        <div class="test-card {status_class}">
            <div class="test-header" onclick="toggleTest('{test_id}')">
                <span class="test-status">{status_icon}</span>
                <span class="test-name">{html.escape(r.test.name)}</span>
                <span class="test-meta">{html.escape(str(r.test.category) if r.test.category else "unknown")} | {html.escape(str(r.test.tier) if r.test.tier else "unknown")} | {r.total_duration:.2f}s</span>
                <span class="test-toggle">&#9660;</span>
            </div>
            <div id="{test_id}" class="test-details" style="display:none">
                <div class="phases">
                    {"".join(phases_html)}
                </div>
            </div>
        </div>
        """)

    # Build diagnostic entries if available
    diag_cards = []
    if hasattr(target, "diagnostics"):
        diag = target.diagnostics
        if diag.entries:
            for d_idx, e in enumerate(diag.entries):
                d_status = "\u2713" if e.success else "\u2717"
                d_class = "phase-success" if e.success else "phase-failure"
                d_id = f"diag-{d_idx}"

                # Get stdout/stderr if available
                logs = ""
                if hasattr(e, "stdout") and e.stdout:
                    logs += f"=== stdout ===\n{e.stdout}\n"
                if hasattr(e, "stderr") and e.stderr:
                    logs += f"=== stderr ===\n{e.stderr}\n"
                if hasattr(e, "details") and e.details:
                    logs += f"=== details ===\n{e.details}\n"
                if not logs:
                    logs = e.message

                diag_cards.append(f"""
                <div class="phase {d_class}" onclick="togglePhase('{d_id}')">
                    <span class="phase-icon">{d_status}</span>
                    <span class="phase-name">{html.escape(e.phase)} / {html.escape(e.layer)} / {html.escape(e.operation)}</span>
                    <span class="phase-duration">{e.duration:.2f}s</span>
                    <span class="phase-toggle">+</span>
                </div>
                <div id="{d_id}" class="phase-logs" style="display:none">
                    <pre>{html.escape(logs)}</pre>
                </div>
                """)

    diag_section = ""
    if diag_cards:
        diag_section = f"""
        <div class="section">
            <h2 onclick="toggleSection('diag-section')" class="section-header">
                Infrastructure Diagnostics
                <span class="section-toggle">&#9660;</span>
            </h2>
            <div id="diag-section" class="phases">
                {"".join(diag_cards)}
            </div>
        </div>
        """

    # Get context info
    ctx = target.diagnostics.context if hasattr(target, "diagnostics") else None
    test_name = ctx.test_name if ctx else "Unknown"
    config_name = ctx.config if ctx else "Unknown"
    run_id = ctx.run_id if ctx else "Unknown"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Hop3 Test Report - {html.escape(test_name)}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 25px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{ margin: 0 0 10px 0; }}
        .meta {{ opacity: 0.8; font-size: 14px; }}
        .stats {{
            display: flex;
            gap: 15px;
            margin-top: 20px;
            flex-wrap: wrap;
        }}
        .stat {{
            background: rgba(255,255,255,0.1);
            padding: 12px 20px;
            border-radius: 8px;
            font-weight: 500;
        }}
        .stat.passed {{ border-left: 4px solid #4caf50; }}
        .stat.failed {{ border-left: 4px solid #f44336; }}
        .section {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .section h2 {{
            margin: 0 0 15px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }}
        .section-header {{
            cursor: pointer;
            user-select: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .section-toggle {{ font-size: 12px; }}

        /* Test cards */
        .test-card {{
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            margin-bottom: 10px;
            overflow: hidden;
        }}
        .test-card.success {{ border-left: 4px solid #4caf50; }}
        .test-card.failure {{ border-left: 4px solid #f44336; background: #fff8f8; }}
        .test-header {{
            padding: 15px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 12px;
            background: #fafafa;
            transition: background 0.2s;
        }}
        .test-header:hover {{ background: #f0f0f0; }}
        .test-status {{
            font-size: 20px;
            font-weight: bold;
        }}
        .test-card.success .test-status {{ color: #4caf50; }}
        .test-card.failure .test-status {{ color: #f44336; }}
        .test-name {{
            font-weight: 600;
            flex: 1;
        }}
        .test-meta {{
            color: #666;
            font-size: 13px;
        }}
        .test-toggle {{
            color: #999;
            font-size: 12px;
        }}
        .test-details {{
            padding: 0 15px 15px 15px;
            border-top: 1px solid #eee;
        }}

        /* Phases */
        .phases {{
            margin-top: 10px;
        }}
        .phase {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 12px;
            margin: 4px 0;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .phase:hover {{ filter: brightness(0.95); }}
        .phase-success {{ background: #e8f5e9; }}
        .phase-failure {{ background: #ffebee; }}
        .phase-icon {{ font-weight: bold; }}
        .phase-success .phase-icon {{ color: #4caf50; }}
        .phase-failure .phase-icon {{ color: #f44336; }}
        .phase-name {{ flex: 1; font-weight: 500; }}
        .phase-duration {{ color: #666; font-size: 12px; }}
        .phase-toggle {{ color: #999; font-size: 14px; min-width: 12px; }}
        /* Inline phases (short content, no foldable section) */
        .phase-inline {{
            cursor: default;
        }}
        .phase-inline:hover {{ filter: none; }}
        .phase-inline .phase-name {{ flex: 0 0 auto; min-width: 100px; }}
        .phase-message {{
            color: #555;
            font-size: 13px;
            flex: 1;
        }}
        .phase-logs {{
            margin: 4px 0 4px 20px;
            border-left: 3px solid #ddd;
        }}
        .phase-logs pre {{
            margin: 0;
            padding: 12px;
            font-size: 12px;
            background: #1a1a2e;
            color: #e0e0e0;
            border-radius: 0 6px 6px 0;
            max-height: 400px;
            overflow: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .error-log {{
            background: #2d1f1f !important;
            color: #ffcdd2 !important;
        }}

        footer {{
            text-align: center;
            color: #666;
            margin-top: 40px;
            padding: 20px;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Hop3 Test Report</h1>
        <div class="meta">
            Test: <strong>{html.escape(test_name)}</strong> |
            Config: {html.escape(config_name)} |
            Run: {html.escape(run_id)}
        </div>
        <div class="stats">
            <div class="stat passed">Passed: {passed}</div>
            <div class="stat failed">Failed: {failed}</div>
            <div class="stat">Total: {total}</div>
            <div class="stat">Duration: {total_duration:.1f}s</div>
        </div>
    </div>

    <div class="section">
        <h2>Test Results</h2>
        <p style="color:#666;font-size:13px;margin-bottom:15px;">
            Click on a test to expand details. Click on each phase to see logs.
        </p>
        {"".join(test_cards)}
    </div>

    {diag_section}

    <footer>
        Generated by hop3-testing at {datetime.now().isoformat()}<br>
        Logs directory: {html.escape(str(log_path))}
    </footer>

    <script>
        function toggleTest(id) {{
            const el = document.getElementById(id);
            const toggle = el.previousElementSibling.querySelector('.test-toggle');
            if (el.style.display === 'none') {{
                el.style.display = 'block';
                toggle.innerHTML = '&#9650;';
            }} else {{
                el.style.display = 'none';
                toggle.innerHTML = '&#9660;';
            }}
        }}

        function togglePhase(id) {{
            const el = document.getElementById(id);
            const toggle = el.previousElementSibling.querySelector('.phase-toggle');
            if (el.style.display === 'none') {{
                el.style.display = 'block';
                toggle.textContent = '-';
            }} else {{
                el.style.display = 'none';
                toggle.textContent = '+';
            }}
            event.stopPropagation();
        }}

        function toggleSection(id) {{
            const el = document.getElementById(id);
            if (el.style.display === 'none') {{
                el.style.display = 'block';
            }} else {{
                el.style.display = 'none';
            }}
        }}

        // Auto-expand failed tests
        document.querySelectorAll('.test-card.failure').forEach(card => {{
            const details = card.querySelector('.test-details');
            const toggle = card.querySelector('.test-toggle');
            if (details) {{
                details.style.display = 'block';
                toggle.innerHTML = '&#9650;';
            }}
        }});
    </script>
</body>
</html>
"""

    # Save HTML report
    html_path = log_path / "report.html"
    html_path.write_text(html_content)
    return html_path


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
    # Find project root and Dockerfile
    root = ctx.obj["root"]
    dockerfile_path = (
        root / "packages" / "hop3-server" / "tests" / "d_e2e" / "docker" / "Dockerfile"
    )

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
        "docker",
        "build",
        "-f",
        str(dockerfile_path),
        "-t",
        tag,
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
        click.echo("  hop3-test-new apps           # Test all apps")
        click.echo("  hop3-test-new apps 010-flask # Test specific app")
    except subprocess.CalledProcessError as e:
        click.echo(f"\nBuild failed with exit code {e.returncode}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo("Docker not found. Please install Docker.", err=True)
        sys.exit(1)


@cli.command("build-test-image")
@click.option("--no-cache", is_flag=True, help="Build without Docker cache")
@click.pass_context
def build_test_image(ctx: click.Context, no_cache: bool) -> None:
    """Pre-build the Docker test image to warm the cache.

    The system tests automatically build a Docker image using docker build.
    Docker caches unchanged layers, so subsequent builds are fast.

    This command pre-builds the image so the first test run is also fast.
    It's optional - the image is built automatically when you run tests.

    Examples:
        hop3-test-new build-test-image              # Build with cache
        hop3-test-new build-test-image --no-cache   # Force full rebuild
    """
    # Find project root and Dockerfile
    root = ctx.obj["root"]
    dockerfile_path = (
        root / "packages" / "hop3-installer" / "docker" / "Dockerfile.base"
    )

    if not dockerfile_path.exists():
        click.echo(f"Dockerfile not found at: {dockerfile_path}", err=True)
        sys.exit(1)

    click.echo(f"\n{'=' * 70}")
    click.echo("Building hop3-test Docker image")
    click.echo("(Docker layer caching will make subsequent builds fast)")
    click.echo(f"{'=' * 70}")
    click.echo(f"\nDockerfile: {dockerfile_path}")
    click.echo()

    # Build command
    cmd = [
        "docker",
        "build",
        "-f",
        str(dockerfile_path),
        "-t",
        "hop3-test:latest",
    ]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(str(root))

    try:
        subprocess.run(cmd, check=True)
        click.echo(f"\n{'=' * 70}")
        click.echo("Successfully built: hop3-test:latest")
        click.echo(f"{'=' * 70}")
        click.echo("\nDocker has cached the image layers.")
        click.echo("System tests will now start faster:")
        click.echo("  make test-system")
        click.echo("  hop3-test-new system")
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
