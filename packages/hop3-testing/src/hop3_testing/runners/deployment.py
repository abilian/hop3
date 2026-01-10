# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deployment test runner."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..apps.catalog import AppSource
from ..apps.deployment import DeploymentSession
from .base import TestResult, ValidationResult

if TYPE_CHECKING:
    from ..catalog.models import TestDefinition
    from ..targets.base import DeploymentTarget


class DeploymentTestRunner:
    """Runs deployment tests using the existing DeploymentSession.

    A deployment test consists of:
    1. Deploy the application to the target via DeploymentSession
    2. Wait for the app to be running
    3. Run HTTP test and check script (via DeploymentSession)
    4. Run additional validations from test.toml
    5. Cleanup (destroy the app)
    """

    def __init__(
        self,
        target: DeploymentTarget,
        cleanup: bool = True,
        verbose: bool = False,
    ):
        """Initialize the runner.

        Args:
            target: The deployment target to run tests on
            cleanup: Whether to destroy apps after testing
            verbose: Whether to print verbose output
        """
        self.target = target
        self.cleanup = cleanup
        self.verbose = verbose

    def run(self, test: TestDefinition) -> TestResult:
        """Run a deployment test.

        Args:
            test: The test definition to run

        Returns:
            TestResult with all validation results
        """
        start_time = time.time()
        validation_results = []
        deploy_logs = ""
        error = None

        try:
            # Get app path
            app_path = test.app_path
            if app_path is None:
                return TestResult(
                    test=test,
                    passed=False,
                    total_duration=time.time() - start_time,
                    error="Test has no app path",
                )

            if not app_path.exists():
                return TestResult(
                    test=test,
                    passed=False,
                    total_duration=time.time() - start_time,
                    error=f"App path does not exist: {app_path}",
                )

            # Convert TestDefinition to AppSource for DeploymentSession
            app_source = self._create_app_source(test)

            if self.verbose:
                print(f"  Deploying {test.name} from {app_path}...")

            # Create deployment session with config
            session_config = {
                "verbose": self.verbose,
                "debug": self.verbose,  # Enable debug in verbose mode
            }
            session = DeploymentSession(
                app=app_source,
                target=self.target,
                config=session_config,
            )

            # Run the deployment and built-in tests
            try:
                # Prepare (copy to temp dir, init git)
                session.prepare()

                # Deploy via RPC
                if not session.deploy():
                    deploy_logs = session._last_deploy_error or "Deployment failed"
                    return TestResult(
                        test=test,
                        passed=False,
                        deploy_logs=deploy_logs,
                        total_duration=time.time() - start_time,
                        error=f"Deploy failed: {deploy_logs}",
                    )

                # Capture success
                validation_results.append(
                    ValidationResult(
                        passed=True,
                        message="Deployment succeeded",
                        duration=time.time() - start_time,
                        validation_type="deploy",
                    )
                )

                # Check if app is deployed
                if not session.check_deployed():
                    return TestResult(
                        test=test,
                        passed=False,
                        validation_results=validation_results,
                        total_duration=time.time() - start_time,
                        error="App not found in deployment list after deploy",
                    )

                validation_results.append(
                    ValidationResult(
                        passed=True,
                        message="App appears in deployment list",
                        duration=0.0,
                        validation_type="deploy_check",
                    )
                )

                # Run HTTP test if app has Procfile
                if app_source.has_procfile:
                    http_start = time.time()
                    http_passed = session.test_http()
                    validation_results.append(
                        ValidationResult(
                            passed=http_passed,
                            message="HTTP test passed"
                            if http_passed
                            else "HTTP test failed",
                            duration=time.time() - http_start,
                            validation_type="http",
                        )
                    )

                    if not http_passed:
                        return TestResult(
                            test=test,
                            passed=False,
                            validation_results=validation_results,
                            total_duration=time.time() - start_time,
                            error="HTTP test failed",
                        )

                # Run check script if present
                if app_source.has_check_script:
                    check_start = time.time()
                    check_passed = session.run_check_script()
                    validation_results.append(
                        ValidationResult(
                            passed=check_passed,
                            message="Check script passed"
                            if check_passed
                            else "Check script failed",
                            duration=time.time() - check_start,
                            validation_type="check_script",
                        )
                    )

                    if not check_passed:
                        return TestResult(
                            test=test,
                            passed=False,
                            validation_results=validation_results,
                            total_duration=time.time() - start_time,
                            error="Check script failed",
                        )

                # Run additional validations from test.toml
                # (The built-in validations above cover the basic cases,
                # but test.toml can specify additional checks)
                for validation in test.validations:
                    if self.verbose:
                        print(f"    Running validation: {validation.type}")
                    # Skip HTTP validations since we already ran test_http()
                    if validation.type == "http":
                        continue

                    # For other validation types, we'd run them here
                    # Currently we only support http validations which are
                    # already covered by session.test_http()

            finally:
                # Cleanup
                if self.cleanup:
                    if self.verbose:
                        print(f"  Cleaning up {test.name}...")
                    session.cleanup()

        except Exception as e:
            error = str(e)
            import traceback

            if self.verbose:
                traceback.print_exc()

        # Determine overall pass/fail
        passed = error is None and all(v.passed for v in validation_results)

        return TestResult(
            test=test,
            passed=passed,
            validation_results=validation_results,
            deploy_logs=deploy_logs,
            total_duration=time.time() - start_time,
            error=error,
        )

    def _create_app_source(self, test: TestDefinition) -> AppSource:
        """Convert a TestDefinition to an AppSource for DeploymentSession.

        Args:
            test: Test definition

        Returns:
            AppSource compatible with DeploymentSession
        """
        app_path = test.app_path
        if app_path is None:
            msg = f"Test {test.name} has no app path"
            raise ValueError(msg)

        # Infer category from test metadata or name
        category = "other"
        if test.metadata.covers:
            # Use first cover tag as category hint
            covers = test.metadata.covers
            if "python" in covers:
                category = "python-simple"
            elif "nodejs" in covers:
                category = "nodejs"
            elif "golang" in covers:
                category = "golang"
            elif "ruby" in covers:
                category = "ruby"

        return AppSource(
            name=test.name,
            path=app_path,
            category=category,
            description=test.description or "",
        )

    def run_multiple(
        self,
        tests: list[TestDefinition],
        fail_fast: bool = False,
    ) -> list[TestResult]:
        """Run multiple tests.

        Args:
            tests: List of test definitions to run
            fail_fast: Stop on first failure

        Returns:
            List of test results
        """
        results = []

        for test in tests:
            result = self.run(test)
            results.append(result)

            if fail_fast and not result.passed:
                break

        return results
