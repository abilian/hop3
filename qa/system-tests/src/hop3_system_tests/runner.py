# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Test runner integration with hop3-testing framework.

This module provides the bridge between the daily system test orchestrator
and the hop3-testing framework, enabling execution of:
- Deployment tests (test apps)
- Demo tests
- Tutorial tests
"""

from __future__ import annotations

import contextlib
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_testing.catalog import Catalog
from hop3_testing.catalog.models import Category, TargetType
from hop3_testing.cli.runners import run_single_test
from hop3_testing.targets import RemoteConfig, RemoteTarget
from hop3_testing.util.console import PrintingConsole, Verbosity
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.runners.base import TestResult

    from .config import Config, TestConfig


@dataclass
class TestSuiteResult:
    """Result of running a test suite."""

    suite_name: str
    """Name of the test suite (e.g., 'test-apps', 'demos')."""

    total: int
    """Total number of tests in the suite."""

    passed: int
    """Number of tests that passed."""

    failed: int
    """Number of tests that failed."""

    skipped: int
    """Number of tests that were skipped."""

    duration: float
    """Total duration in seconds."""

    test_results: list[TestResult] = field(default_factory=list)
    """Individual test results."""

    errors: list[str] = field(default_factory=list)
    """Suite-level errors (e.g., catalog load failures)."""

    @property
    def success(self) -> bool:
        """True if all tests passed."""
        return self.failed == 0 and len(self.errors) == 0

    @property
    def summary(self) -> str:
        """Get a summary string for the suite result."""
        status = "PASS" if self.success else "FAIL"
        return (
            f"[{status}] {self.suite_name}: "
            f"{self.passed}/{self.total} passed, "
            f"{self.failed} failed, "
            f"{self.skipped} skipped "
            f"({self.duration:.1f}s)"
        )


@dataclass
class AllSuitesResult:
    """Result of running all test suites."""

    suite_results: list[TestSuiteResult] = field(default_factory=list)
    """Results from each test suite."""

    total_duration: float = 0.0
    """Total duration across all suites."""

    @property
    def success(self) -> bool:
        """True if all suites passed."""
        return all(s.success for s in self.suite_results)

    @property
    def total_tests(self) -> int:
        """Total number of tests across all suites."""
        return sum(s.total for s in self.suite_results)

    @property
    def total_passed(self) -> int:
        """Total number of tests that passed."""
        return sum(s.passed for s in self.suite_results)

    @property
    def total_failed(self) -> int:
        """Total number of tests that failed."""
        return sum(s.failed for s in self.suite_results)

    @property
    def total_skipped(self) -> int:
        """Total number of tests that were skipped."""
        return sum(s.skipped for s in self.suite_results)

    def get_failed_tests(self) -> list[TestResult]:
        """Get all failed tests across all suites."""
        failed = []
        for suite in self.suite_results:
            failed.extend(r for r in suite.test_results if not r.passed)
        return failed


class TestRunnerManager:
    """Manages test execution using hop3-testing framework.

    This class bridges the daily system test framework with hop3-testing,
    providing:
    - Test catalog loading and filtering
    - Remote target connection management
    - Test execution with progress reporting
    - Result aggregation

    Example:
        runner = TestRunnerManager(
            host="192.168.1.100",
            config=test_config,
            project_root=Path("/path/to/hop3"),
        )
        result = runner.run_all_suites()
    """

    # Map suite names to categories
    SUITE_CATEGORIES = {
        "test-apps": Category.DEPLOYMENT,
        "docker-apps": Category.DOCKER_APP,
        "native-apps": Category.NATIVE_APP,
        "demos": Category.DEMO,
        "tutorials": Category.TUTORIAL,
    }

    def __init__(
        self,
        host: str,
        config: TestConfig,
        project_root: Path | None = None,
        console: Console | None = None,
        verbose: bool = False,
    ):
        """Initialize the test runner manager.

        Args:
            host: Target server hostname or IP address.
            config: Test configuration.
            project_root: Path to Hop3 project root (for catalog scanning).
                         If None, attempts to auto-detect.
            console: Rich console for output.
            verbose: Enable verbose output.
        """
        self.host = host
        self.config = config
        self.project_root = project_root or self._find_project_root()
        self.console = console or Console()
        self.verbose = verbose

        self._catalog: Catalog | None = None
        self._target: RemoteTarget | None = None
        self._printing_console = PrintingConsole()
        if verbose:
            self._printing_console.set_verbosity(Verbosity.VERBOSE)

    def run_all_suites(self) -> AllSuitesResult:
        """Run all configured test suites.

        Returns:
            AllSuitesResult with results from all suites.
        """
        start_time = time.time()
        result = AllSuitesResult()

        try:
            # Load catalog
            self._load_catalog()

            # Create remote target
            self._create_target()

            # Run each configured suite
            for suite_name in self.config.suites:
                try:
                    suite_result = self._run_suite(suite_name)
                    result.suite_results.append(suite_result)

                    # Fail fast if configured
                    if self.config.fail_fast and not suite_result.success:
                        self.console.print(
                            f"  [yellow]Fail fast enabled, stopping after {suite_name}[/yellow]"
                        )
                        break

                except Exception as e:
                    # Handle suite-level exceptions
                    self.console.print(
                        f"  [red]Suite {suite_name} failed with exception: {e}[/red]"
                    )
                    result.suite_results.append(
                        TestSuiteResult(
                            suite_name=suite_name,
                            total=0,
                            passed=0,
                            failed=1,
                            skipped=0,
                            duration=0,
                            errors=[f"Suite exception: {e}"],
                        )
                    )
                    # Continue with next suite unless fail_fast is enabled
                    if self.config.fail_fast:
                        break

        except Exception as e:
            # Log the error but preserve any results we've collected
            import traceback

            error_msg = f"Suite execution error: {e}"
            self.console.print(f"  [red]{error_msg}[/red]")
            if self.verbose:
                self.console.print(traceback.format_exc())

            # Create an error result only if we have no results yet
            if not result.suite_results:
                result.suite_results.append(
                    TestSuiteResult(
                        suite_name="setup",
                        total=0,
                        passed=0,
                        failed=0,
                        skipped=0,
                        duration=0,
                        errors=[error_msg],
                    )
                )

        finally:
            self._cleanup_target()
            result.total_duration = time.time() - start_time

        return result

    def run_suite(self, suite_name: str) -> TestSuiteResult:
        """Run a single test suite.

        Args:
            suite_name: Name of the suite to run (test-apps, demos, tutorials).

        Returns:
            TestSuiteResult with the suite results.
        """
        try:
            self._load_catalog()
            self._create_target()
            return self._run_suite(suite_name)
        finally:
            self._cleanup_target()

    def _run_suite(self, suite_name: str) -> TestSuiteResult:
        """Execute a single test suite.

        Args:
            suite_name: Name of the suite to run.

        Returns:
            TestSuiteResult with the suite results.
        """
        start_time = time.time()
        self.console.print(f"\n[bold]Running suite: {suite_name}[/bold]")

        # Get category for this suite
        category = self.SUITE_CATEGORIES.get(suite_name)
        if not category:
            return TestSuiteResult(
                suite_name=suite_name,
                total=0,
                passed=0,
                failed=0,
                skipped=0,
                duration=0,
                errors=[f"Unknown suite: {suite_name}"],
            )

        # Get tests for this category
        tests = self._get_tests_for_suite(category, suite_name)
        if not tests:
            self.console.print(
                f"  [yellow]No tests found for suite: {suite_name}[/yellow]"
            )
            return TestSuiteResult(
                suite_name=suite_name,
                total=0,
                passed=0,
                failed=0,
                skipped=0,
                duration=time.time() - start_time,
            )

        # Randomize order if requested
        if self.config.random_order:
            tests = list(tests)  # Make a copy to avoid mutating original
            random.shuffle(tests)
            self.console.print(f"  Found {len(tests)} tests (randomized)")
        else:
            self.console.print(f"  Found {len(tests)} tests")

        # Run tests
        test_results = []
        passed = 0
        failed = 0
        skipped = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task(f"Running {suite_name}...", total=len(tests))

            for test in tests:
                progress.update(task, description=f"[{test.name}]")

                # Check if test can run on remote target
                if not test.can_run_on(TargetType.REMOTE):
                    skipped += 1
                    progress.advance(task)
                    continue

                # Run the test with exception handling
                try:
                    result = self._run_single_test(test)
                    test_results.append(result)

                    if result.passed:
                        passed += 1
                        self.console.print(f"  [green]✓[/green] {test.name}")
                    else:
                        failed += 1
                        # Truncate very long error messages for display
                        error_msg = result.error or "validation failed"
                        if len(error_msg) > 200:
                            error_msg = error_msg[:200] + "..."
                        self.console.print(f"  [red]✗[/red] {test.name}: {error_msg}")

                except Exception as e:
                    # Handle unexpected exceptions during test execution
                    failed += 1
                    error_msg = str(e)
                    if len(error_msg) > 200:
                        error_msg = error_msg[:200] + "..."
                    self.console.print(
                        f"  [red]✗[/red] {test.name}: Exception: {error_msg}"
                    )
                    # Create a failed result for this test
                    from hop3_testing.runners.base import TestResult

                    test_results.append(
                        TestResult(test=test, passed=False, error=str(e))
                    )

                progress.advance(task)

                # Fail fast check
                if self.config.fail_fast and failed > 0:
                    skipped += len(tests) - (passed + failed + skipped)
                    break

        duration = time.time() - start_time
        return TestSuiteResult(
            suite_name=suite_name,
            total=len(tests),
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration=duration,
            test_results=test_results,
        )

    def _get_tests_for_suite(
        self,
        category: Category,
        suite_name: str,
    ) -> list[TestDefinition]:
        """Get tests for a specific suite, with optional filtering.

        Args:
            category: Test category to filter by.
            suite_name: Suite name for additional filtering.

        Returns:
            List of test definitions to run.
        """
        if not self._catalog:
            return []

        # Get tests by category
        tests = self._catalog.filter(
            categories=[category.value],
            targets=[TargetType.REMOTE.value],
        )

        # Apply docker_apps_subset filter for test-apps suite
        if suite_name == "test-apps" and self.config.docker_apps_subset:
            subset = set(self.config.docker_apps_subset)
            tests = [t for t in tests if t.name in subset]

        return tests

    def _run_single_test(self, test: TestDefinition) -> TestResult:
        """Run a single test using hop3-testing framework.

        Args:
            test: Test definition to run.

        Returns:
            TestResult from the test execution.
        """
        if not self._target:
            from hop3_testing.runners.base import TestResult

            return TestResult(
                test=test,
                passed=False,
                error="Target not initialized",
            )

        try:
            return run_single_test(
                test=test,
                target=self._target,
                cleanup=True,
                verbose=self.verbose,
                console=self._printing_console,
                debug=self.verbose,
            )
        except Exception as e:
            from hop3_testing.runners.base import TestResult

            return TestResult(
                test=test,
                passed=False,
                error=f"Test execution error: {e}",
            )

    def _load_catalog(self) -> None:
        """Load the test catalog."""
        if self._catalog is not None:
            return

        self.console.print("Loading test catalog...")
        self._catalog = Catalog(self.project_root)
        self._catalog.scan()

        total_tests = len(self._catalog)
        errors = self._catalog.errors()
        if errors:
            self.console.print(
                f"  [yellow]Loaded {total_tests} tests with {len(errors)} errors[/yellow]"
            )
        else:
            self.console.print(f"  Loaded {total_tests} tests")

    def _create_target(self) -> None:
        """Create and start the remote target.

        Uses SSH tunnel authentication - exactly like a real user would.
        No server modifications, no shortcuts.
        """
        if self._target is not None:
            return

        self.console.print(f"Connecting to remote target: {self.host}")

        # Create remote config - connect-only mode (no deployment)
        remote_config = RemoteConfig(
            host=self.host,
            port=22,
            user="root",
        )

        self._target = RemoteTarget(remote_config)
        try:
            self._target.start()

            # Force SSH tunnel mode by clearing api_url from target info
            # This makes the hop3 CLI use ssh:// URL instead of http:// with JWT
            # SSH tunnel provides implicit authentication via SSH keys
            # This is exactly how a real user would interact with hop3
            if self._target._info:
                from dataclasses import replace

                self._target._info = replace(self._target._info, api_url="")

            self.console.print("  [green]Connected (SSH authentication)[/green]")

        except Exception as e:
            self.console.print(f"  [red]Connection failed: {e}[/red]")
            self._target = None
            raise

    def _cleanup_target(self) -> None:
        """Cleanup the remote target connection."""
        if self._target:
            with contextlib.suppress(Exception):
                self._target.stop()
            self._target = None

    def _find_project_root(self) -> Path:
        """Find the Hop3 monorepo root directory.

        Returns:
            Path to the project root.
        """
        import os

        # Try environment variable first
        if hop3_root := os.environ.get("HOP3_PROJECT_ROOT"):
            return Path(hop3_root)

        # Try to find by looking for the hop3 monorepo structure
        # Start from current directory and go up
        current = Path.cwd()
        for _ in range(10):
            # Look for the monorepo markers: apps/test-apps and packages/hop3-server
            if (current / "apps" / "test-apps").exists() and (
                current / "packages" / "hop3-server"
            ).exists():
                return current

            # Also check for pyproject.toml with hop3 workspace
            pyproject = current / "pyproject.toml"
            if pyproject.exists():
                content = pyproject.read_text()
                if "hop3-server" in content and "hop3-cli" in content:
                    return current

            parent = current.parent
            if parent == current:
                break
            current = parent

        # Fallback to current directory
        return Path.cwd()


def run_tests(
    host: str,
    config: Config,
    console: Console | None = None,
    verbose: bool = False,
) -> AllSuitesResult:
    """Run all tests against a deployed Hop3 server.

    Convenience function that creates a TestRunnerManager and runs all suites.

    Args:
        host: Target server hostname or IP address.
        config: Full configuration.
        console: Rich console for output.
        verbose: Enable verbose output.

    Returns:
        AllSuitesResult with results from all suites.
    """
    # Find project root from deployment config if using local repo
    project_root = None
    if config.deployment.use_local_repo and config.deployment.local_repo_path:
        project_root = config.deployment.local_repo_path

    runner = TestRunnerManager(
        host=host,
        config=config.tests,
        project_root=project_root,
        console=console,
        verbose=verbose,
    )
    return runner.run_all_suites()
