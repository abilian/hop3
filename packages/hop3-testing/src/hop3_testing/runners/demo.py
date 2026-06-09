# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Demo test runner.

Runs demo scripts (demo-script.py) or declarative demos defined in test.toml.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from hop3_testing.catalog.models import Validation, ValidationExpect
from hop3_testing.exceptions import TargetOutOfDiskError
from hop3_testing.util import build_test_env
from hop3_testing.util.console import Console, PrintingConsole, Verbosity

from .base import TestResult, ValidationResult
from .validations import run_validation

if TYPE_CHECKING:
    from hop3_testing.catalog.models import DemoStep, TestDefinition
    from hop3_testing.targets.base import DeploymentTarget


@dataclass(frozen=True)
class DemoTestRunner:
    """Runs demo tests.

    A demo test can be either:
    - Script-based: Runs a demo-script.py file
    - Declarative: Executes steps defined in test.toml

    Script-based demos are expected to have a run(ctx) function that
    receives a context object with target and configuration.
    """

    target: DeploymentTarget
    """The deployment target."""

    cleanup: bool = True
    """Whether to cleanup after test."""

    verbose: bool = False
    """Whether to print verbose output."""

    console: Console = field(default_factory=PrintingConsole)
    """Console for output."""

    def __post_init__(self) -> None:
        """Set verbosity after initialization."""
        if self.verbose:
            self.console.set_verbosity(Verbosity.VERBOSE)

    def run(self, test: TestDefinition) -> TestResult:
        """Run a demo test.

        Args:
            test: The test definition

        Returns:
            TestResult with all validation results
        """
        if test.demo is None:
            return TestResult(
                test=test,
                passed=False,
                error="Test has no demo configuration",
            )

        if test.demo.type == "declarative":
            return self._run_declarative(test)
        return self._run_script(test)

    def _run_script(self, test: TestDefinition) -> TestResult:
        """Run a script-based demo.

        Demos are run using the demos' own infrastructure (demos/demo.py CLI),
        which provides the proper context, backends, and utilities that demo
        scripts expect.

        Args:
            test: The test definition

        Returns:
            TestResult
        """
        assert test.demo is not None  # Checked by caller (run method)

        start_time = time.time()
        validation_results: list[ValidationResult] = []
        error = None
        logs = ""

        # Preconditions live outside the try below: path lookups can't raise
        # the subprocess exceptions we catch, so keeping them inside would
        # obscure where those exceptions actually come from.
        resolved = self._resolve_demo_cli(test)
        if isinstance(resolved, TestResult):
            return resolved
        demos_root, demo_cli = resolved

        self.console.info(f"Running demo: {test.name}")
        cmd = self._build_demo_command(demo_cli, test)
        self.console.debug(f"Running: {' '.join(cmd)}")

        # Only the subprocess call can raise the exceptions we catch.
        try:
            result = subprocess.run(
                cmd,
                cwd=demos_root,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                env=build_test_env(self.target.info),
                check=False,
            )
        except subprocess.TimeoutExpired:
            error = "Demo script timed out"
        except Exception as e:
            error = str(e)
        else:
            logs = result.stdout + result.stderr
            if result.returncode != 0:
                log_tail = logs[-2000:] if len(logs) > 2000 else logs
                error = (
                    f"Demo failed with exit code {result.returncode}\n\n"
                    f"--- Output (last 2000 chars) ---\n{log_tail}"
                )
                self.console.error(f"Demo {test.name} failed")
            else:
                self.console.success("Demo script completed successfully")

        passed = error is None and all(v.passed for v in validation_results)

        return TestResult(
            test=test,
            passed=passed,
            validation_results=validation_results,
            deploy_logs=logs,
            total_duration=time.time() - start_time,
            error=error,
        )

    def _resolve_demo_cli(self, test: TestDefinition) -> tuple[Path, Path] | TestResult:
        """Resolve (demos_root, demo_cli) or return a short-circuit TestResult.

        Pure path-existence checks; no I/O beyond ``Path.exists()``. Lives
        outside ``_run_script``'s try-block so the protected region matches
        the subprocess.run that actually does the work.
        """
        assert test.demo is not None  # checked by caller
        if test.source_path is None:
            return TestResult(test=test, passed=False, error="Test has no source path")

        demo_dir = test.source_path.parent
        script_path = demo_dir / (test.demo.script or "demo-script.py")
        if not script_path.exists():
            return TestResult(
                test=test,
                passed=False,
                error=f"Demo script not found: {script_path}",
            )

        demos_root = self._find_demos_root(demo_dir)
        if demos_root is None:
            return TestResult(
                test=test,
                passed=False,
                error="Could not find demos root directory",
            )

        demo_cli = demos_root / "demo.py"
        if not demo_cli.exists():
            return TestResult(
                test=test, passed=False, error=f"Demo CLI not found: {demo_cli}"
            )
        return demos_root, demo_cli

    def _build_demo_command(self, demo_cli: Path, test: TestDefinition) -> list[str]:
        """Build the argv to invoke the demos CLI for a given test."""
        cmd = [sys.executable, str(demo_cli)]
        target_info = self.target.info
        if target_info.ssh_host:
            cmd.extend(["--host", target_info.ssh_host])
            if target_info.ssh_user and target_info.ssh_user != "root":
                cmd.extend(["--ssh-user", target_info.ssh_user])
        else:
            cmd.extend(["--backend", "docker"])

        cmd.extend(["--skip-install", "--fail-fast"])
        if self.verbose:
            cmd.append("--verbose")
        cmd.append(test.deploy_name)  # e.g. "demo03"
        return cmd

    def _find_demos_root(self, demo_dir: Path) -> Path | None:
        """Find the demos root directory containing demo.py.

        Walks up from the demo directory to find the demos/ root.

        Args:
            demo_dir: Starting directory (e.g., demos/demo03)

        Returns:
            Path to demos root, or None if not found
        """
        current = demo_dir
        for _ in range(5):  # Max 5 levels up
            if (current / "demo.py").exists() and (current / "lib").is_dir():
                return current
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    def _run_declarative(self, test: TestDefinition) -> TestResult:
        """Run a declarative demo.

        Args:
            test: The test definition

        Returns:
            TestResult
        """
        start_time = time.time()
        validation_results = []
        error = None
        logs = ""
        deployed_apps: list[str] = []

        try:
            if test.demo is None or not test.demo.steps:
                return TestResult(
                    test=test,
                    passed=False,
                    error="No demo steps defined",
                )

            demo_dir = test.source_path.parent if test.source_path else Path.cwd()

            for i, step in enumerate(test.demo.steps):
                self.console.progress(
                    f"Step {i + 1}: {step.action}", i + 1, len(test.demo.steps)
                )

                step_result = self._run_step(step, demo_dir, deployed_apps)

                if step_result is not None:
                    validation_results.append(step_result)

                    if not step_result.passed:
                        error = f"Step {i + 1} ({step.action}) failed: {step_result.message}"
                        break

        except Exception as e:
            error = str(e)

        finally:
            # Cleanup deployed apps
            if self.cleanup:
                for app_name in deployed_apps:
                    with contextlib.suppress(Exception):
                        self.target.destroy_app(app_name)

        passed = error is None and all(v.passed for v in validation_results)

        return TestResult(
            test=test,
            passed=passed,
            validation_results=validation_results,
            deploy_logs=logs,
            total_duration=time.time() - start_time,
            error=error,
        )

    def _run_deploy_step(
        self,
        step: DemoStep,
        demo_dir: Path,
        deployed_apps: list[str],
        start_time: float,
    ) -> ValidationResult | None:
        """Handle deploy action."""
        if not step.app_path or not step.app_name:
            return ValidationResult(
                validation=Validation(type="command"),
                passed=False,
                message="Deploy step requires app_path and app_name",
                duration=time.time() - start_time,
            )

        # Reclaim disk before deploying (demos share one long-lived target
        # across many deploys, so artifacts accumulate fastest here).
        try:
            self.target.ensure_disk_headroom()
        except TargetOutOfDiskError as e:
            return ValidationResult(
                validation=Validation(type="command"),
                passed=False,
                message=str(e),
                duration=time.time() - start_time,
            )

        app_path = demo_dir / step.app_path
        result = self.target.deploy_app(app_path, step.app_name)
        deployed_apps.append(step.app_name)

        if not result.success:
            return ValidationResult(
                validation=Validation(type="command"),
                passed=False,
                message=result.error or "Deploy failed",
                duration=time.time() - start_time,
            )

        if not self.target.wait_for_app(step.app_name):
            return ValidationResult(
                validation=Validation(type="command"),
                passed=False,
                message="App did not start",
                duration=time.time() - start_time,
            )
        return None

    def _run_command_step(self, step: DemoStep, start_time: float) -> ValidationResult:
        """Handle command action."""
        if not step.run:
            return ValidationResult(
                validation=Validation(type="command"),
                passed=False,
                message="Command step requires 'run' field",
                duration=time.time() - start_time,
            )

        exit_code, _stdout, _stderr = self.target.exec_run(step.run)
        expected_exit = (
            step.expect_exit_code if step.expect_exit_code is not None else 0
        )

        return ValidationResult(
            validation=Validation(type="command", run=step.run),
            passed=(exit_code == expected_exit),
            message="OK"
            if exit_code == expected_exit
            else f"Command exited with {exit_code}, expected {expected_exit}",
            duration=time.time() - start_time,
        )

    def _run_step(
        self,
        step: DemoStep,
        demo_dir: Path,
        deployed_apps: list[str],
    ) -> ValidationResult | None:
        """Run a single demo step.

        Args:
            step: The step to run
            demo_dir: Demo directory
            deployed_apps: List to track deployed apps

        Returns:
            ValidationResult if step produces a validation, None otherwise
        """
        start_time = time.time()

        if step.action == "deploy":
            return self._run_deploy_step(step, demo_dir, deployed_apps, start_time)

        if step.action == "wait":
            time.sleep(step.seconds)
            return None

        if step.action == "validate":
            # Cast to Literal type expected by Validation
            validation_type = cast(
                "Literal['http', 'command', 'script', 'demo-script', 'validoc']",
                step.validation_type or "http",
            )
            validation = Validation(
                type=validation_type,
                url=step.url,
                expect=ValidationExpect(
                    status=step.expect_status, contains=step.expect_contains
                ),
            )
            return run_validation(
                validation=validation,
                target=self.target,
                app_name=deployed_apps[-1] if deployed_apps else "",
                app_url=step.url or self.target.info.http_base,
            )

        if step.action == "destroy":
            if step.app_name:
                # Best effort cleanup
                with contextlib.suppress(Exception):
                    self.target.destroy_app(step.app_name)
                if step.app_name in deployed_apps:
                    deployed_apps.remove(step.app_name)
            return None

        if step.action == "command":
            return self._run_command_step(step, start_time)

        return None
