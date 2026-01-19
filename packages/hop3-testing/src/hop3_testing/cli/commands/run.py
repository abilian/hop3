# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Run command (backwards compatible with original hop3-test)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from hop3_testing.catalog import Catalog
from hop3_testing.catalog.loader import generate_test_definition_from_app
from hop3_testing.cli.helpers import create_target_with_options
from hop3_testing.cli.runners import run_app_tests

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition


def _select_tests(
    catalog: Catalog,
    apps: tuple[str, ...],
    category: str | None,
) -> list[TestDefinition]:
    """Select tests based on command arguments."""
    if apps:
        tests = []
        for app_name in apps:
            test = catalog.get_test(app_name)
            if test:
                tests.append(test)
            else:
                app_path = Path(app_name)
                if app_path.exists():
                    tests.append(generate_test_definition_from_app(app_path))
                else:
                    click.echo(f"Warning: Test not found: {app_name}", err=True)
        return tests
    if category:
        return catalog.filter(categories=[category])
    return list(catalog.all_tests())


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
@click.option(
    "--report",
    type=click.Choice(["none", "text", "html"]),
    default="text",
    help="Report format",
)
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode")
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
    report: str,
    quiet: bool,
) -> None:
    """Run tests (backwards compatible with original hop3-test).

    This command provides the same interface as the original hop3-test CLI.
    You can specify apps by name or path, or use --category to filter.

    Examples:
        hop3-test run --target docker
        hop3-test run 010-flask-pip-wsgi 020-nodejs-express
        hop3-test run --category python-simple
    """
    # Enable verbose if debug mode
    if debug:
        ctx.obj["verbose"] = True

    catalog = Catalog(ctx.obj["root"])
    catalog.scan()

    tests = _select_tests(catalog, apps, category)

    if not tests:
        click.echo("No tests found to run")
        sys.exit(1)

    if not quiet:
        click.echo(f"\nFound {len(tests)} test(s) to run")
        for t in tests:
            click.echo(f"  - {t.name} ({t.category.value})")

    target_obj = create_target_with_options(
        target_type=target,
        host=host,
        port=port,
        user=user,
        ssh_key=ssh_key,
        use_cache=use_cache,
        force_rebuild=force_rebuild,
    )

    # Delegate to existing runner logic (avoids code duplication)
    # run_app_tests handles: start target, run tests, save results, report, stop
    run_app_tests(
        ctx=ctx,
        tests=tests,
        target=target_obj,
        keep=keep or keep_target,  # keep_target implies keeping apps too
        fail_fast=fail_fast,
        report=report,
        quiet=quiet,
    )
