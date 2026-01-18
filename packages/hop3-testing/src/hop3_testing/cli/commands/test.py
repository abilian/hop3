# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test commands (package, system, apps)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from hop3_testing.catalog import Catalog
from hop3_testing.catalog.loader import generate_test_definition_from_app
from hop3_testing.cli.runners import run_app_tests, run_system_tests
from hop3_testing.results import ConsoleReporter
from hop3_testing.runners import DeploymentTestRunner
from hop3_testing.selector import Selector, get_mode_config
from hop3_testing.targets import DockerTarget, RemoteTarget
from hop3_testing.targets.config import DeploymentConfig, DockerConfig, RemoteConfig


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
) -> None:
    """Test Hop3 system using real hop3-deploy.

    This command deploys Hop3 using the actual hop3-deploy infrastructure,
    then runs tests against it. This ensures tests exercise the real
    installation and deployment paths.

    Examples:
        hop3-test system --docker                  # Deploy local code to Docker
        hop3-test system --docker --mode ci        # Include medium-tier tests
        hop3-test system --docker --deploy-from git --branch main
        hop3-test system --docker --clean          # Clean install
        hop3-test system --docker --reuse          # Reuse existing container

        hop3-test system --ssh --host server.com   # Deploy to remote via SSH
        hop3-test system --ssh                     # Uses HOP3_TEST_HOST env var
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

    # Load catalog and select tests based on mode
    catalog = Catalog(ctx.obj["root"])
    catalog.scan()

    mode_config = get_mode_config(mode)
    selector = Selector(catalog)
    tests = selector.select_for_target(mode_config, target_type)

    if not tests:
        click.echo("No tests found")
        return

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
    click.echo(f"Tests to run: {len(tests)}")

    # Build deployment config (None if reusing existing)
    deployment: DeploymentConfig | None = None
    if deploy_from != "none":
        deployment = DeploymentConfig(
            source=deploy_from,  # type: ignore[arg-type]
            branch=branch,
            clean=clean,
            verbose=verbose,
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
        hop3-test apps                      # Test all apps against ready image
        hop3-test apps 010-flask            # Test specific app
        hop3-test apps --category python    # Test by category
        hop3-test apps --target remote --host X  # Against remote server
    """
    verbose = ctx.obj["verbose"]

    # Load catalog
    catalog = Catalog(ctx.obj["root"])
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

    # Create target (no deployment - app testing uses pre-deployed servers)
    target_obj: DockerTarget | RemoteTarget
    if target in {"ready", "docker"}:
        # Both use DockerTarget with pre-built image (no deployment)
        docker_config = DockerConfig(
            image=image if target == "ready" else "hop3-ready:latest",
            container_name="hop3-app-test",
        )
        target_obj = DockerTarget(docker_config)
    else:
        # Remote target (connect-only, no deployment)
        if not host:
            click.echo("--host required for remote target", err=True)
            sys.exit(1)
        assert host is not None  # Type narrowing after sys.exit
        remote_config = RemoteConfig(
            host=host,
            port=port,
            user=user,
            ssh_key=ssh_key,
        )
        target_obj = RemoteTarget(remote_config)

    # Run tests
    run_app_tests(ctx, tests, target_obj, keep, fail_fast, report, quiet)
