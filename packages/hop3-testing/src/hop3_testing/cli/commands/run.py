# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Run command (backwards compatible with original hop3-test)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from hop3_testing.catalog import TestCatalog
from hop3_testing.catalog.loader import generate_test_definition_from_app
from hop3_testing.cli.helpers import create_target_with_options
from hop3_testing.cli.runners import run_single_test
from hop3_testing.results import ConsoleReporter, ResultStore

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition


def _select_tests(
    catalog: TestCatalog,
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


def _report_test_result(test, result) -> None:
    """Report the result of a single test."""
    if result.passed:
        click.echo(f"\n✓ {test.name} PASSED")
    else:
        click.echo(f"\n❌ {test.name} FAILED")
        if result.error:
            click.echo(f"  Error: {result.error}")


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
        hop3-test run --target docker
        hop3-test run 010-flask-pip-wsgi 020-nodejs-express
        hop3-test run --category python-simple
    """
    verbose = ctx.obj["verbose"]

    catalog = TestCatalog(ctx.obj["root"])
    catalog.scan()

    tests = _select_tests(catalog, apps, category)

    if not tests:
        click.echo("No tests found to run")
        sys.exit(1)

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

            _report_test_result(test, result)

            if fail_fast and not result.passed:
                click.echo("\nFail fast enabled, stopping tests")
                break

        store.finish_run()
        reporter.summary(results)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        sys.exit(0 if failed == 0 else 1)

    finally:
        if not keep_target:
            click.echo("\nStopping target...")
            target_obj.stop()
