# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test execution logic for the CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hop3_testing.apps.debug import DeploymentDebugger
from hop3_testing.results import ConsoleReporter, ResultStore
from hop3_testing.runners import (
    DemoTestRunner,
    DeploymentTestRunner,
    TutorialTestRunner,
)
from hop3_testing.util.console import PrintingConsole, Verbosity

from .logging import TestLogWriter
from .reports import generate_reports

if TYPE_CHECKING:
    import click

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


def _filter_by_available_services(
    tests: list[TestDefinition],
    available_features: list[str],
    console: Console,
) -> list[TestDefinition]:
    """Filter out tests whose required services aren't in --with features.

    Maps feature names to service names (e.g., "nix" feature satisfies
    "nix" service requirement). Tests with no service requirements always pass.
    """
    if not available_features:
        return tests

    # Normalize: "all" means everything is available
    if "all" in available_features:
        return tests

    # Split comma-separated features (e.g., "nix,mysql,redis" → 3 items)
    available: set[str] = set()
    for feat in available_features:
        available.update(part.strip() for part in feat.split(","))

    # Map common aliases
    if "postgres" in available:
        available.add("postgresql")
    if "postgresql" in available:
        available.add("postgres")

    filtered = []
    for test in tests:
        required = set(test.requirements.services)
        missing = required - available
        if missing:
            console.warning(
                f"Skipping {test.name}: requires {', '.join(sorted(missing))} "
                f"(not in --with {', '.join(sorted(available_features))})"
            )
        else:
            filtered.append(test)
    return filtered


def _resolve_logs_dir(logs_dir: str | None, mode_label: str) -> Path | None:
    """Pick the per-test log directory.

    Default: ``test-logs/<mode>-<timestamp>/app-logs`` so failures
    always have an on-disk pointer. Pass ``--logs-dir off`` to
    disable.
    """
    if logs_dir == "off":
        return None
    if logs_dir:
        return Path(logs_dir)

    from datetime import datetime, timezone  # noqa: PLC0415

    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path("test-logs") / f"{mode_label}-{stamp}" / "app-logs"


def run_tests(
    ctx: click.Context,
    tests: list[TestDefinition],
    target: DeploymentTarget,
    *,
    keep: bool,
    fail_fast: bool,
    report: str = "text",
    quiet: bool = False,
    debug: bool = False,
    logs_dir: str | None = None,
    start_message: str = "Starting tests...",
    mode_label: str = "system",
    available_features: list[str] | None = None,
) -> None:
    """Run tests against a target.

    This is the single test execution function used by all CLI commands.
    The target is started, tests are executed, results are collected and reported.
    """
    # Sort tests by name for deterministic, alphabetical execution order
    tests = sorted(tests, key=lambda t: t.name)

    verbose = ctx.obj["verbose"]
    console = _create_console(verbose, quiet)

    # Filter out tests whose required services aren't available
    if available_features is not None:
        tests = _filter_by_available_services(tests, available_features, console)
        if not tests:
            console.error("No tests remaining after filtering by available services")
            sys.exit(1)
    store = ResultStore()

    log_path = _resolve_logs_dir(logs_dir, mode_label)
    reporter = ConsoleReporter(verbose=verbose, quiet=quiet, logs_dir=log_path)
    log_writer = TestLogWriter(log_path)

    if log_writer.enabled:
        console.status(f"Per-app logs: {log_path}/")

    try:
        console.status(start_message)
        target.start()
    except RuntimeError as e:
        console.error(f"Failed: {e}")
        sys.exit(1)

    try:
        store.start_run(
            mode=mode_label,
            target_type=mode_label,
            target_name=target.info.ssh_host,
        )

        results = []
        for test in tests:
            console.status(f"[{test.name}] ", details=None)

            result = run_single_test(
                test,
                target,
                cleanup=not keep,
                verbose=verbose,
                console=console,
                debug=debug,
            )
            results.append(result)
            store.save(result)
            log_writer.write_test_log(result)
            reporter.report_test(result)

            if fail_fast and not result.passed:
                console.warning("Fail fast enabled, stopping tests")
                break

        store.finish_run()
        reporter.summary(results)
        generate_reports(target, report, results)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        sys.exit(0 if failed == 0 else 1)

    finally:
        if not keep:
            console.status("Stopping target...")
            target.stop()


def run_single_test(
    test: TestDefinition,
    target: DeploymentTarget,
    cleanup: bool,
    verbose: bool,
    console: Console | None = None,
    debug: bool = False,
) -> TestResult:
    """Run a single test with the appropriate runner."""
    common_kwargs: dict[str, Any] = {"cleanup": cleanup, "verbose": verbose}
    if console is not None:
        common_kwargs["console"] = console

    runner: DemoTestRunner | TutorialTestRunner | DeploymentTestRunner
    if test.demo is not None:
        runner = DemoTestRunner(target, **common_kwargs)
    elif test.tutorial is not None:
        runner = TutorialTestRunner(target, **common_kwargs)
    else:
        runner = DeploymentTestRunner(target, **common_kwargs)

    result = runner.run(test)

    if debug and not result.passed:
        actual_console = console or PrintingConsole()
        # Use the real deployed app name (with timestamp suffix)
        # when available; fall back to the test name only for
        # runners that don't populate it. Using test.name directly
        # points the debugger at a nonexistent path (the test path
        # rather than ``<basename>-<timestamp>``).
        app_name = result.deployed_app_name or test.name
        debugger = DeploymentDebugger(
            target=target,
            app_name=app_name,
            console=actual_console,
        )
        deployment_type = "auto"
        if test.deployment and test.deployment.type:
            deployment_type = test.deployment.type
        debugger.show_all_rich(deployment_type)

    return result
