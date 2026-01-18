# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test execution logic for the CLI."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import click

from hop3_testing.catalog import Catalog
from hop3_testing.catalog.models import Category
from hop3_testing.results import ConsoleReporter, ResultStore
from hop3_testing.runners import (
    DemoTestRunner,
    DeploymentTestRunner,
    TutorialTestRunner,
)
from hop3_testing.selector import Selector, get_mode_config
from hop3_testing.util.console import PrintingConsole, Verbosity

from .helpers import create_target
from .reports import generate_reports

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.runners.base import TestResult
    from hop3_testing.targets.base import DeploymentTarget
    from hop3_testing.util.console import Console


def _create_console(verbose: bool, quiet: bool = False) -> Console:
    """Create a console with appropriate verbosity level."""
    console = PrintingConsole()
    if quiet:
        console.set_verbosity(Verbosity.QUIET)
    elif verbose:
        console.set_verbosity(Verbosity.VERBOSE)
    return console


def run_system_tests(
    ctx: click.Context,
    tests: list[TestDefinition],
    target: DeploymentTarget,
    keep: bool,
    fail_fast: bool,
    report: str = "text",
    quiet: bool = False,
) -> None:
    """Run system tests with full deployment."""
    verbose = ctx.obj["verbose"]
    console = _create_console(verbose, quiet)
    store = ResultStore()
    reporter = ConsoleReporter(verbose=verbose, quiet=quiet)

    try:
        console.status("Deploying Hop3 via hop3-deploy...")
        target.start()
    except RuntimeError as e:
        # Clean exit for expected errors (deployment failures, port conflicts, etc.)
        console.error(f"Deployment failed: {e}")
        sys.exit(1)

    try:
        store.start_run(
            mode="system",
            target_type="docker-deploy",
            target_name=target.info.ssh_host,
        )

        results = []
        for test in tests:
            console.status(f"[{test.name}] ", details=None)

            result = run_single_test(
                test, target, cleanup=True, verbose=verbose, console=console
            )
            results.append(result)
            store.save(result)

            reporter.report_test(result)

            if fail_fast and not result.passed:
                console.warning("Fail fast enabled, stopping tests")
                break

        store.finish_run()
        reporter.summary(results)

        # Generate reports based on --report option
        generate_reports(target, report, results)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        sys.exit(0 if failed == 0 else 1)

    finally:
        if not keep:
            console.status("Stopping target...")
            target.stop()


def run_app_tests(
    ctx: click.Context,
    tests: list[TestDefinition],
    target: DeploymentTarget,
    keep: bool,
    fail_fast: bool,
    report: str = "text",
    quiet: bool = False,
) -> None:
    """Run app tests against pre-deployed server."""
    verbose = ctx.obj["verbose"]
    console = _create_console(verbose, quiet)
    store = ResultStore()
    reporter = ConsoleReporter(verbose=verbose, quiet=quiet)

    try:
        console.status("Starting test environment...")
        target.start()
    except RuntimeError as e:
        # Clean exit for expected errors (e.g., image not found)
        console.error(f"Error: {e}")
        sys.exit(1)

    try:
        store.start_run(
            mode="apps",
            target_type="ready",
            target_name=target.info.ssh_host,
        )

        results = []
        for test in tests:
            console.status(f"[{test.name}] ", details=None)

            result = run_single_test(
                test, target, cleanup=not keep, verbose=verbose, console=console
            )
            results.append(result)
            store.save(result)

            reporter.report_test(result)

            if fail_fast and not result.passed:
                console.warning("Fail fast enabled, stopping tests")
                break

        store.finish_run()
        reporter.summary(results)

        # Generate reports based on --report option
        generate_reports(target, report, results)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        sys.exit(0 if failed == 0 else 1)

    finally:
        console.status("Stopping target...")
        target.stop()


def run_tests(
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
    console = _create_console(verbose)

    # Load catalog
    catalog = Catalog(ctx.obj["root"])
    catalog.scan()

    # Get mode config and select tests
    mode_config = get_mode_config(mode)
    selector = Selector(catalog)
    tests = selector.select_for_target(mode_config, target_type)

    if not tests:
        console.warning("No tests to run")
        return

    console.status(f"Running {len(tests)} tests in {mode} mode")

    # Create target
    target = create_target(target_type, host, verbose=verbose)

    # Initialize result storage
    store = ResultStore()
    reporter = ConsoleReporter(verbose=verbose)

    try:
        console.status("Starting test environment...")
        target.start()
    except RuntimeError as e:
        # Clean exit for expected errors (deployment failures, port conflicts, etc.)
        console.error(f"Deployment failed: {e}")
        sys.exit(1)

    try:
        store.start_run(
            mode=mode,
            target_type=target_type,
            target_name=target.info.ssh_host,
        )

        # Run tests
        results = []
        for test in tests:
            console.status(f"[{test.name}] ", details=None)

            result = run_single_test(
                test, target, cleanup=not keep_apps, verbose=verbose, console=console
            )
            results.append(result)
            store.save(result)

            reporter.report_test(result)

            if fail_fast and not result.passed:
                console.warning("Fail fast enabled, stopping tests")
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
            console.status("Stopping test environment...")
            target.stop()


def run_single_test(
    test: TestDefinition,
    target: DeploymentTarget,
    cleanup: bool,
    verbose: bool,
    console: Console | None = None,
) -> TestResult:
    """Run a single test with the appropriate runner."""
    # Build common kwargs, only include console if provided
    common_kwargs: dict[str, Any] = {"cleanup": cleanup, "verbose": verbose}
    if console is not None:
        common_kwargs["console"] = console

    if test.category == Category.DEMO:
        runner = DemoTestRunner(target, **common_kwargs)
    elif test.category == Category.TUTORIAL:
        runner = TutorialTestRunner(target, **common_kwargs)
    else:
        # Default to deployment runner for deployment category and any others
        runner = DeploymentTestRunner(target, **common_kwargs)

    return runner.run(test)
