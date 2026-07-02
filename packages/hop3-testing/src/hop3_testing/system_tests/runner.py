# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Test runner integration with hop3-testing framework.

This module provides the bridge between the cloud system-test path and the
hop3-testing framework, enabling execution of:
- Deployment tests (test apps)
- Demo tests
- Tutorial tests
"""

from __future__ import annotations

import contextlib
import random
import time
import traceback
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from hop3_testing.catalog import Catalog
from hop3_testing.catalog.models import TargetType
from hop3_testing.cli.runners import run_single_test
from hop3_testing.runners.base import TestResult
from hop3_testing.targets import RemoteConfig, RemoteTarget
from hop3_testing.util import find_project_root
from hop3_testing.util.console import PrintingConsole, Verbosity
from hop3_testing.util.ssh import SSHConnection, SSHConnectionInfo

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition

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
        failed: list[TestResult] = []
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

    # Infer runner type from the suite path
    _RUNNER_TYPE_KEYWORDS: ClassVar[dict[str, str]] = {
        "demos": "demo",
        "tutorials": "tutorial",
    }
    _DEFAULT_RUNNER_TYPE = "deployment"

    def __init__(
        self,
        host: str,
        config: TestConfig,
        project_root: Path | None = None,
        console: Console | None = None,
        verbose: bool = False,
        logs_dir: Path | None = None,
    ):
        """Initialize the test runner manager.

        Args:
            host: Target server hostname or IP address.
            config: Test configuration.
            project_root: Path to Hop3 project root (for catalog scanning).
                         If None, attempts to auto-detect.
            console: Rich console for output.
            verbose: Enable verbose output.
            logs_dir: Directory for diagnostic logs. If set, logs are collected
                     immediately when tests fail (before cleanup).
        """
        self.host = host
        self.config = config
        self.project_root = project_root or find_project_root()
        self.console = console or Console()
        self.verbose = verbose
        self.logs_dir = logs_dir

        self._catalog: Catalog | None = None
        self._target: RemoteTarget | None = None
        self._ssh_conn: SSHConnection | None = None
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
            # Load catalog only for the configured suites
            self._load_catalog(self.config.suites)

            if self._catalog is not None and len(self._catalog) == 0:
                self.console.print(
                    "[red]Error: No tests found for suites: "
                    f"{', '.join(self.config.suites)}[/red]"
                )
                self.console.print(
                    f"  Configured suites: {', '.join(self.config.suites)}"
                )
                return result

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
            self._load_catalog([suite_name])
            self._create_target()
            return self._run_suite(suite_name)
        finally:
            self._cleanup_target()

    def _run_suite(self, suite_name: str) -> TestSuiteResult:  # noqa: PLR0915, C901, PLR0912
        """Execute a single test suite.

        Args:
            suite_name: Name of the suite to run.

        Returns:
            TestSuiteResult with the suite results.
        """
        start_time = time.time()
        self.console.print(f"\n[bold]Running suite: {suite_name}[/bold]")

        # Infer runner type from the suite path
        runner_type = self._DEFAULT_RUNNER_TYPE
        for keyword, rtype in self._RUNNER_TYPE_KEYWORDS.items():
            if keyword in suite_name:
                runner_type = rtype
                break

        # Get tests for this runner type
        tests = self._get_tests_for_suite(runner_type, suite_name)
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
                        # Collect diagnostics IMMEDIATELY before cleanup happens
                        self._collect_failed_test_diagnostics(test.name)

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
                    test_results.append(
                        TestResult(test=test, passed=False, error=str(e))
                    )
                    # Collect diagnostics for exception failures too
                    self._collect_failed_test_diagnostics(test.name)

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
        runner_type: str,
        suite_name: str,
    ) -> list[TestDefinition]:
        """Get tests for a specific suite, with optional filtering.

        Args:
            runner_type: Runner type to filter by (deployment, demo, tutorial).
            suite_name: Suite name for additional filtering.

        Returns:
            List of test definitions to run.
        """
        if not self._catalog:
            return []

        # Get tests by target, then filter by runner type
        tests = self._catalog.filter(
            targets=[TargetType.REMOTE.value],
        )
        tests = [t for t in tests if t.runner_type == runner_type]

        # Filter tests to those belonging to this suite's path
        if suite_name:
            tests = [
                t for t in tests if t.source_path and suite_name in str(t.source_path)
            ]

        # Apply docker_apps_subset filter
        if self.config.docker_apps_subset:
            subset = set(self.config.docker_apps_subset)
            tests = [t for t in tests if t.name in subset]

        return sorted(tests, key=lambda t: t.name)

    def _run_single_test(self, test: TestDefinition) -> TestResult:
        """Run a single test using hop3-testing framework.

        Args:
            test: Test definition to run.

        Returns:
            TestResult from the test execution.
        """
        if not self._target:
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
            return TestResult(
                test=test,
                passed=False,
                error=f"Test execution error: {e}",
            )

    def _load_catalog(self, scan_paths: list[str]) -> None:
        """Load the test catalog for the given paths.

        Args:
            scan_paths: Paths relative to project root to scan for test.toml files.
        """
        self.console.print("Loading test catalog...")
        self._catalog = Catalog(self.project_root)
        self._catalog.scan(paths=scan_paths)

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
            if self._target._info:  # noqa: SLF001
                self._target._info = replace(self._target._info, api_url="")  # noqa: SLF001

            self.console.print("  [green]Connected (SSH authentication)[/green]")

        except Exception as e:
            self.console.print(f"  [red]Connection failed: {e}[/red]")
            self._target = None
            raise

    def _cleanup_target(self) -> None:
        """Cleanup the remote target connection."""
        if self._ssh_conn:
            with contextlib.suppress(Exception):
                self._ssh_conn.close()
            self._ssh_conn = None
        if self._target:
            with contextlib.suppress(Exception):
                self._target.stop()
            self._target = None

    def _collect_failed_test_diagnostics(self, test_name: str) -> None:
        """Collect diagnostics for a failed test immediately.

        This runs BEFORE the app is cleaned up, so we can capture logs.

        Args:
            test_name: Name of the failed test (used as app name).
        """
        if not self.logs_dir:
            return

        try:  # noqa: PLW0717 — best-effort diagnostic collector called from a `finally` elsewhere: by design it catches *anything* the SSH/file ops throw and prints a warning. Narrowing the try would let an exception abort log collection partway and lose the rest of the diagnostics.
            # Ensure SSH connection
            if not self._ssh_conn:
                info = SSHConnectionInfo(host=self.host, user="root")
                self._ssh_conn = SSHConnection(info)
                if not self._ssh_conn.connect(timeout=30):
                    self.console.print(
                        "  [yellow]Could not connect for diagnostics[/yellow]"
                    )
                    return

            # Create output directory for this test
            failed_apps_dir = self.logs_dir / "failed-apps"
            failed_apps_dir.mkdir(parents=True, exist_ok=True)

            # Extract basename from path-style test names
            # e.g., "apps/real-apps-nix/cryptpad" -> "cryptpad"
            base_name = Path(test_name).name

            # Find the app directory on the server (might have timestamp suffix)
            find_cmd = f"find /home/hop3/apps -maxdepth 1 -name '{base_name}*' -type d 2>/dev/null | head -1"
            _exit_code, stdout, _ = self._ssh_conn.run(find_cmd, timeout=10)
            app_path = stdout.strip()

            if not app_path:
                # No app directory found - create a minimal log with test name
                app_log_dir = failed_apps_dir / base_name
                app_log_dir.mkdir(exist_ok=True)
                (app_log_dir / "NOT_FOUND.txt").write_text(
                    f"App directory not found on server for {test_name}\n"
                    f"Searched for: {test_name}* in /home/hop3/apps/\n"
                )
                return

            # Use the actual app directory name (with timestamp suffix)
            app_name = Path(app_path).name
            app_log_dir = failed_apps_dir / app_name
            app_log_dir.mkdir(exist_ok=True)

            # Collect diagnostic files
            log_commands = {
                "build.log": f"cat {app_path}/log/build.log 2>&1",
                "app.log": f"cat {app_path}/log/*.log 2>&1",
                "env": f"cat {app_path}/ENV 2>&1",
                "hop3.toml": f"cat {app_path}/src/hop3.toml 2>&1",
                "Procfile": f"cat {app_path}/src/Procfile 2>&1",
                "Dockerfile": f"cat {app_path}/src/Dockerfile 2>&1",
                "docker-compose.yml": f"cat {app_path}/src/docker-compose.yml 2>&1 || cat {app_path}/src/docker-compose.yaml 2>&1",
                "nginx.conf": f"cat /home/hop3/nginx/{app_name}.conf 2>&1 || cat /etc/nginx/sites-enabled/{app_name}* 2>&1",
                # uWSGI configs use pattern: {app_name}_{kind}.{ordinal}.ini
                "uwsgi.ini": f"cat /home/hop3/uwsgi-enabled/{app_name}*.ini 2>&1 || cat /home/hop3/uwsgi-available/{app_name}*.ini 2>&1",
                "uwsgi-all.log": f"cat /home/hop3/apps/{app_name}/log/*.log 2>&1 | tail -200",
                "journal-hop3-server.log": "journalctl -u hop3-server -n 100 --no-pager 2>&1",
                "journal-uwsgi.log": "journalctl -u uwsgi-hop3 -n 100 --no-pager 2>&1",
                "process-info.txt": f"ps aux | grep -E '{app_name}|uwsgi' | grep -v grep 2>&1",
                "port-info.txt": f"cat {app_path}/PORT 2>&1 && ss -tlnp | grep $(cat {app_path}/PORT 2>/dev/null) 2>&1",
                "directory-tree.txt": f"find {app_path} -type f 2>&1 | head -100",
                # Debug: Check Python environment on the server
                "python-debug.txt": f"echo '=== Python versions ==='; which python3 python3.11 python3.12 2>&1; python3 --version 2>&1; echo '=== Hop3 venv ==='; /home/hop3/venv/bin/python3 --version 2>&1; echo '=== App venv ==='; {app_path}/venv/bin/python3 --version 2>&1; echo '=== uWSGI info ==='; /home/hop3/venv/bin/uwsgi --python-version 2>&1",
                # Debug: Check if Flask can be imported in app venv
                "flask-import-test.txt": f"{app_path}/venv/bin/python3 -c 'import flask; print(flask.__version__)' 2>&1 || echo 'Flask import failed'",
                # Debug: List app venv packages
                "venv-packages.txt": f"{app_path}/venv/bin/pip list 2>&1 || echo 'pip list failed'",
            }

            collected = []
            for filename, cmd in log_commands.items():
                try:
                    _exit_code, stdout, _stderr = self._ssh_conn.run(cmd, timeout=10)
                    content = stdout.strip()
                    # Skip empty or error-only content
                    if not content or content.startswith("cat:"):
                        continue
                    if "No such file or directory" in content and len(content) < 100:
                        continue
                    (app_log_dir / filename).write_text(stdout)
                    collected.append(filename)
                except Exception:
                    pass

            if collected:
                abs_path = app_log_dir.resolve()
                self.console.print(
                    f"  [dim]Diagnostics ({len(collected)} files): {abs_path}[/dim]"
                )

        except Exception as e:
            self.console.print(
                f"  [yellow]Error collecting diagnostics for {test_name}: {e}[/yellow]"
            )


def run_tests(
    host: str,
    config: Config,
    console: Console | None = None,
    verbose: bool = False,
    logs_dir: Path | None = None,
) -> AllSuitesResult:
    """Run all tests against a deployed Hop3 server.

    Convenience function that creates a TestRunnerManager and runs all suites.

    Args:
        host: Target server hostname or IP address.
        config: Full configuration.
        console: Rich console for output.
        verbose: Enable verbose output.
        logs_dir: Directory for diagnostic logs (collected on test failures).

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
        logs_dir=logs_dir,
    )
    return runner.run_all_suites()
