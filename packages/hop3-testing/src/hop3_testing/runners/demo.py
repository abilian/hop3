# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Demo test runner.

Runs demo scripts (demo-script.py) or declarative demos defined in test.toml.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .base import TestResult, ValidationResult
from .validations import run_validation

if TYPE_CHECKING:
    from hop3_testing.catalog.models import DemoStep, TestDefinition
    from hop3_testing.targets.base import DeploymentTarget


class DemoTestRunner:
    """Runs demo tests.

    A demo test can be either:
    - Script-based: Runs a demo-script.py file
    - Declarative: Executes steps defined in test.toml

    Script-based demos are expected to have a run(ctx) function that
    receives a context object with target and configuration.
    """

    def __init__(
        self,
        target: DeploymentTarget,
        cleanup: bool = True,
        verbose: bool = False,
    ):
        """Initialize the runner.

        Args:
            target: The deployment target
            cleanup: Whether to cleanup after test
            verbose: Whether to print verbose output
        """
        self.target = target
        self.cleanup = cleanup
        self.verbose = verbose

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

        Args:
            test: The test definition

        Returns:
            TestResult
        """
        start_time = time.time()
        validation_results = []
        error = None
        logs = ""

        try:
            # Find the demo script
            if test.source_path is None:
                return TestResult(
                    test=test,
                    passed=False,
                    error="Test has no source path",
                )

            demo_dir = test.source_path.parent
            script_path = demo_dir / (test.demo.script or "demo-script.py")

            if not script_path.exists():
                return TestResult(
                    test=test,
                    passed=False,
                    error=f"Demo script not found: {script_path}",
                )

            if self.verbose:
                print(f"  Running demo script: {script_path}")

            # Create context for the demo
            ctx = DemoContext(
                target=self.target,
                demo_dir=demo_dir,
                verbose=self.verbose,
            )

            # Run the demo script
            # Option 1: Import and call run() function
            # Option 2: Execute as subprocess
            # We'll use subprocess for isolation
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=demo_dir,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                env={
                    **dict(subprocess.os.environ),
                    "HOP3_TEST_HOST": self.target.info.ssh_host,
                    "HOP3_TEST_PORT": str(self.target.info.ssh_port),
                    "HOP3_TEST_SSH_KEY": self.target.info.ssh_key or "",
                },
            )

            logs = result.stdout + result.stderr

            if result.returncode != 0:
                error = f"Demo script failed with exit code {result.returncode}"
                if self.verbose:
                    print(f"  Script output:\n{logs}")
            else:
                if self.verbose:
                    print("  Demo script completed successfully")

                # Run validations if script passed
                for validation in test.validations:
                    val_result = run_validation(
                        validation=validation,
                        target=self.target,
                        app_name=test.name,
                        app_url=self.target.info.http_base,
                    )
                    validation_results.append(val_result)

        except subprocess.TimeoutExpired:
            error = "Demo script timed out"
        except Exception as e:
            error = str(e)

        passed = error is None and all(v.passed for v in validation_results)

        return TestResult(
            test=test,
            passed=passed,
            validation_results=validation_results,
            deploy_logs=logs,
            total_duration=time.time() - start_time,
            error=error,
        )

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
                if self.verbose:
                    print(f"  Step {i + 1}: {step.action}")

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
                    try:
                        self.target.destroy_app(app_name)
                    except Exception:
                        pass

        passed = error is None and all(v.passed for v in validation_results)

        return TestResult(
            test=test,
            passed=passed,
            validation_results=validation_results,
            deploy_logs=logs,
            total_duration=time.time() - start_time,
            error=error,
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
        from hop3_testing.catalog.models import Validation, ValidationExpect

        start_time = time.time()

        if step.action == "deploy":
            # Deploy an app
            if not step.app_path or not step.app_name:
                return ValidationResult(
                    validation=Validation(type="command"),
                    passed=False,
                    message="Deploy step requires app_path and app_name",
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

            # Wait for app
            if not self.target.wait_for_app(step.app_name):
                return ValidationResult(
                    validation=Validation(type="command"),
                    passed=False,
                    message="App did not start",
                    duration=time.time() - start_time,
                )

            return None  # No validation result for deploy

        if step.action == "wait":
            # Just wait
            time.sleep(step.seconds)
            return None

        if step.action == "validate":
            # Run validation
            validation = Validation(
                type=step.validation_type or "http",
                url=step.url,
                expect=ValidationExpect(
                    status=step.expect_status,
                    contains=step.expect_contains,
                ),
            )

            return run_validation(
                validation=validation,
                target=self.target,
                app_name=deployed_apps[-1] if deployed_apps else "",
                app_url=step.url or self.target.info.http_base,
            )

        if step.action == "destroy":
            # Destroy an app
            if step.app_name:
                self.target.destroy_app(step.app_name)
                if step.app_name in deployed_apps:
                    deployed_apps.remove(step.app_name)
            return None

        if step.action == "command":
            # Run a command
            if not step.run:
                return ValidationResult(
                    validation=Validation(type="command"),
                    passed=False,
                    message="Command step requires 'run' field",
                    duration=time.time() - start_time,
                )

            exit_code, stdout, stderr = self.target.exec_run(step.run)

            expected_exit = (
                step.expect_exit_code if step.expect_exit_code is not None else 0
            )

            if exit_code != expected_exit:
                return ValidationResult(
                    validation=Validation(type="command", run=step.run),
                    passed=False,
                    message=f"Command exited with {exit_code}, expected {expected_exit}",
                    duration=time.time() - start_time,
                )

            return ValidationResult(
                validation=Validation(type="command", run=step.run),
                passed=True,
                message="OK",
                duration=time.time() - start_time,
            )

        return None


class DemoContext:
    """Context passed to demo scripts."""

    def __init__(
        self,
        target: DeploymentTarget,
        demo_dir: Path,
        verbose: bool = False,
    ):
        self.target = target
        self.demo_dir = demo_dir
        self.verbose = verbose

    def deploy(self, app_path: str, app_name: str) -> bool:
        """Deploy an application."""
        result = self.target.deploy_app(
            self.demo_dir / app_path,
            app_name,
        )
        return result.success

    def destroy(self, app_name: str) -> bool:
        """Destroy an application."""
        return self.target.destroy_app(app_name)

    def run_command(self, *args: str):
        """Run a hop3 command."""
        return self.target.run_command(*args)

    def http_get(self, url: str):
        """Make an HTTP GET request."""
        return self.target.http_request("GET", url)
