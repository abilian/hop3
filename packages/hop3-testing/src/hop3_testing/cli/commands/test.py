# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test commands (package, system, apps)."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from hop3_testing.catalog import TestCatalog
from hop3_testing.catalog.loader import generate_test_definition_from_app
from hop3_testing.cli.runners import run_app_tests, run_system_tests
from hop3_testing.results import ConsoleReporter
from hop3_testing.runners import DeploymentTestRunner
from hop3_testing.selector import TestSelector, get_mode_config
from hop3_testing.targets import (
    DockerDeployTarget,
    DockerTarget,
    ReadyTarget,
    RemoteDeployTarget,
    RemoteTarget,
)


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


@click.command("system")
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
    run_system_tests(ctx, tests, target_obj, keep, fail_fast, report, quiet)


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
    run_app_tests(ctx, tests, target_obj, keep, fail_fast, report, quiet)
