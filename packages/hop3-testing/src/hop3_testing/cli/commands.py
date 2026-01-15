# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for hop3-testing."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click

from hop3_testing.catalog import TestCatalog
from hop3_testing.catalog.loader import generate_test_definition_from_app
from hop3_testing.results import ConsoleReporter, ResultStore
from hop3_testing.runners import DeploymentTestRunner
from hop3_testing.selector import TestSelector, get_mode_config
from hop3_testing.targets import (
    DockerDeployTarget,
    DockerTarget,
    ReadyTarget,
    RemoteDeployTarget,
    RemoteTarget,
)

from .helpers import create_target_with_options
from .runners import run_app_tests, run_single_test, run_system_tests, run_tests


def register_commands(cli: click.Group) -> None:
    """Register all commands with the CLI group."""
    cli.add_command(list_tests)
    cli.add_command(show_test)
    cli.add_command(dev)
    cli.add_command(ci)
    cli.add_command(nightly)
    cli.add_command(run_command)
    cli.add_command(package)
    cli.add_command(system_test)
    cli.add_command(apps_test)
    cli.add_command(build_ready_image)
    cli.add_command(build_test_image)


@click.command("list")
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


@click.command("show")
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


@click.command("dev")
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
    run_tests(
        ctx,
        mode="dev",
        target_type=target,
        host=host,
        keep_target=keep,
        keep_apps=keep_apps,
        fail_fast=fail_fast,
    )


@click.command("ci")
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
    run_tests(
        ctx,
        mode="ci",
        target_type=target,
        host=host,
        keep_target=False,
        keep_apps=False,
        fail_fast=fail_fast,
    )


@click.command("nightly")
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
    run_tests(
        ctx,
        mode="nightly",
        target_type=target,
        host=host,
        keep_target=False,
        keep_apps=False,
        fail_fast=fail_fast,
    )


@click.command("run")
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
    target_obj = create_target_with_options(
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

            result = run_single_test(
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


@click.command("build-ready-image")
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
        subprocess.run(cmd, check=True)
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


@click.command("build-test-image")
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
