# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test command: deploy Hop3 and run tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import click

from hop3_testing.catalog import Catalog, default_scan_paths
from hop3_testing.catalog.loader import load_test_definition_smart
from hop3_testing.cli.runners import run_tests
from hop3_testing.selector import Selector, get_mode_config, list_modes
from hop3_testing.selector.modes import MODE_ALIASES
from hop3_testing.targets import DockerTarget, RemoteTarget
from hop3_testing.targets.config import DeploymentConfig, DockerConfig, RemoteConfig

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition


def _mode_choices() -> list[str]:
    """Valid ``--mode`` values: the current profiles plus back-compat aliases.

    Dynamic (not a hardcoded list) so renamed/added profiles — including custom
    ones from the Test Lab — are always accepted. The old hardcoded list is what
    silently rejected the renamed `smoke`/`curated`/`full` profiles.
    """
    return sorted(set(list_modes()) | set(MODE_ALIASES))


def _resolve_tests(
    app_names: tuple[str, ...],
    root: Path,
    mode: str,
    target_type: str,
) -> list[TestDefinition]:
    """Resolve app_names into a list of TestDefinitions.

    Handles three cases:
    - Specific paths/names given -> look them up
    - Scan directories given -> scan and return all
    - Nothing given -> use mode-based selection on default paths
    """
    if not app_names:
        # No args: scan everything, use mode-based selection
        catalog = Catalog(root)
        catalog.scan(paths=default_scan_paths(root))
        mode_config = get_mode_config(mode)
        selector = Selector(catalog)
        return selector.select_for_target(mode_config, target_type)

    # Split args into scan directories vs specific apps
    scan_paths: list[str] = []
    direct_apps: list[str] = []
    for name in app_names:
        path = Path(name)
        if path.is_dir() and not (path / "hop3.toml").exists():
            scan_paths.append(name)
        else:
            direct_apps.append(name)

    tests: list[TestDefinition] = []
    catalog = Catalog(root)

    # Scan directories
    if scan_paths:
        catalog.scan(paths=scan_paths)
        tests.extend(catalog.filter())

    # Look up specific apps
    if direct_apps:
        if not scan_paths:
            # Need a catalog for name lookups
            parent_paths = list({str(Path(a).parent) for a in direct_apps if "/" in a})
            if parent_paths:
                catalog.scan(paths=parent_paths)

        for name in direct_apps:
            test, error = _lookup_test(name, catalog)
            if test:
                tests.append(test)
            elif error:
                click.echo(f"Warning: {error}", err=True)

    return tests


def _lookup_test(
    name: str, catalog: Catalog
) -> tuple[TestDefinition | None, str | None]:
    """Look up a test by name or path."""
    # Try path-based lookup
    if "/" in name or Path(name).is_dir():
        path = Path(name.rstrip("/"))
        test = catalog.get_test_by_path(path)
        if test:
            return test, None

        # Try loading directly from the directory
        if path.is_dir() and (
            (path / "hop3.toml").exists() or (path / "test.toml").exists()
        ):
            try:
                return load_test_definition_smart(path), None
            except Exception as e:
                return None, f"Failed to load {path}: {e}"

    # Try name-based lookup
    test = catalog.get_test(name)
    if test:
        return test, None

    # Try directory basename
    if "/" in name:
        test = catalog.get_test(Path(name).name)
        if test:
            return test, None

    return None, f"Test not found: {name}"


# `run` is the canonical name (ADR 052 D9): deploy to one target and run the
# catalog. `system` stays registered as an alias (see register_commands). The
# function keeps its historical name.
@click.command("run")
@click.argument("app_names", nargs=-1)
# Target type
@click.option(
    "--docker", "target_type", flag_value="docker", help="Test using Docker container"
)
@click.option(
    "--ssh", "target_type", flag_value="remote", help="Test using SSH to remote host"
)
# Deployment. `--from` is the canonical spelling (ADR 052 D3); `--deploy-from`
# stays accepted (same dest) so existing callers keep working.
@click.option(
    "--from",
    "--deploy-from",
    "deploy_from",
    type=click.Choice(["local", "git", "pypi", "none"]),
    default="local",
    help="Install source: local | git | pypi | none (reuse existing)",
)
@click.option("--reuse", is_flag=True, help="Reuse existing deployment (skip deploy)")
@click.option("--branch", default="devel", help="Git branch (if --deploy-from git)")
@click.option("--clean", is_flag=True, help="Clean install (remove existing)")
# Connection
@click.option("--host", help="Remote host (for --ssh)")
@click.option("--port", type=int, default=22, help="SSH port")
@click.option("--user", default="root", help="SSH user")
# `--identity` is the canonical name (like `ssh -i`); `--ssh-key` stays as an
# accepted alias. HOP3_SSH_KEY is the canonical env; HOP3_TEST_SSH_KEY still works.
@click.option(
    "--identity",
    "--ssh-key",
    "ssh_key",
    envvar=["HOP3_SSH_KEY", "HOP3_TEST_SSH_KEY"],
    help="SSH private key path (like `ssh -i`; default: $HOP3_SSH_KEY)",
)
# Test options
@click.option(
    "--mode",
    type=click.Choice(_mode_choices()),
    default="smoke",
    help="Test profile (filters by tier/priority, or an explicit curated list)",
)
@click.option("--keep", is_flag=True, help="Keep target and apps after tests")
@click.option("-x", "--fail-fast", is_flag=True, help="Stop on first failure")
@click.option(
    "--report",
    type=click.Choice(["none", "text", "html"]),
    default="text",
    help="Report format",
)
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode")
@click.option("--debug", is_flag=True, help="Show debug info on failure")
@click.option(
    "--narrate",
    is_flag=True,
    help="Print a per-test phase-timing breakdown (where the wall-clock went)",
)
@click.option("--logs-dir", type=click.Path(), help="Directory for per-app logs")
@click.option(
    "--with",
    "features",
    multiple=True,
    help="Features to install (e.g., nix, mysql, redis, or 'all')",
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
    narrate: bool,
    logs_dir: str | None,
    features: tuple[str, ...],
) -> None:
    """Deploy Hop3 and run tests.

    Pass directories to scan or specific app paths/names.
    With --reuse, skips deployment (tests against existing server).

    \b
    Examples:
      hop3-test run --docker                  # Deploy + test defaults
      hop3-test run --docker apps/test-apps   # Scan a directory
      hop3-test run --docker --clean --with all demos
      hop3-test run --ssh --host X            # Remote
      hop3-test run --ssh demos/demo03        # Specific app
      hop3-test run --reuse --ssh --host X    # Skip deploy
    """
    verbose = ctx.obj["verbose"]

    if not target_type:
        click.echo("Error: Must specify --docker or --ssh", err=True)
        click.echo("\nExamples:")
        click.echo("  hop3-test run --docker")
        click.echo("  hop3-test run --ssh --host server.com")
        sys.exit(1)

    assert target_type is not None

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

    # Resolve tests
    root = ctx.obj["root"]
    tests = _resolve_tests(app_names, root, mode, target_type)

    if not tests:
        click.echo("No tests found")
        if app_names:
            click.echo(f"Searched: {', '.join(app_names)}")
        return

    # Show plan
    click.echo(f"\n{'=' * 70}")
    if deploy_from == "none":
        click.echo("Testing against existing Hop3 server")
    else:
        click.echo("Deploy Hop3 + run tests")
    click.echo(f"{'=' * 70}")
    click.echo(f"\nTarget: {target_type}")
    if host:
        click.echo(f"Host: {host}")
    if deploy_from != "none":
        click.echo(f"Deploy from: {deploy_from}")
        if clean:
            click.echo("Clean install: True")
        if features:
            click.echo(f"Features: {', '.join(features)}")
    click.echo(f"\nTests to run ({len(tests)}):")
    for t in tests:
        click.echo(f"  - {t.name}")
    click.echo("")

    # Build deployment config
    deployment: DeploymentConfig | None = None
    if deploy_from != "none":
        deployment = DeploymentConfig(
            source=cast("Literal['local', 'git', 'pypi']", deploy_from),
            branch=branch,
            clean=clean,
            verbose=verbose,
            features=list(features),
        )

    # Create target
    target_obj: DockerTarget | RemoteTarget
    if target_type == "docker":
        docker_config = DockerConfig(
            container_name="hop3-system-test",
            reuse_container=deploy_from == "none",
        )
        target_obj = DockerTarget(docker_config, deployment=deployment)
    else:
        assert host is not None
        remote_config = RemoteConfig(
            host=host,
            port=port,
            user=user,
            ssh_key=ssh_key,
        )
        target_obj = RemoteTarget(remote_config, deployment=deployment)

    # Run tests
    start_msg = (
        "Connecting to existing server..."
        if deploy_from == "none"
        else "Deploying Hop3 via hop3-deploy..."
    )
    run_tests(
        ctx,
        tests,
        target_obj,
        keep=keep,
        fail_fast=fail_fast,
        report=report,
        quiet=quiet,
        debug=debug,
        narrate=narrate,
        logs_dir=logs_dir,
        start_message=start_msg,
        mode_label="system" if deploy_from != "none" else "reuse",
        selection_mode=mode,  # smoke/ci/broad/full -> the dashboard "scope"
        available_features=list(features) if features else None,
    )
