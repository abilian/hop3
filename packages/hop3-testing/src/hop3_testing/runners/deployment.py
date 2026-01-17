# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deployment test runner."""

from __future__ import annotations

import time
import traceback
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from hop3_testing.apps.catalog import AppSource
from hop3_testing.apps.deployment import DeploymentSession

from .base import TestResult, ValidationResult

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.targets.base import DeploymentTarget


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

    def _run_http_test(
        self, session: DeploymentSession, validation_results: list[ValidationResult]
    ) -> str | None:
        """Run HTTP test and return error message if failed, None otherwise."""
        http_start = time.time()
        http_result = session.test_http_detailed()
        validation_results.append(
            ValidationResult(
                passed=http_result["passed"],
                message=http_result["message"],
                duration=time.time() - http_start,
                validation_type="http",
                details=http_result.get("details"),
            )
        )
        if not http_result["passed"]:
            return http_result["message"]
        return None

    def _run_check_script(
        self, session: DeploymentSession, validation_results: list[ValidationResult]
    ) -> str | None:
        """Run check script and return error message if failed, None otherwise."""
        target_info = self.target.info
        parsed_http = urlparse(target_info.http_base)
        is_remote_target = parsed_http.hostname not in {"localhost", "127.0.0.1"}

        if is_remote_target:
            validation_results.append(
                ValidationResult(
                    passed=True,
                    message="Check script skipped (remote target)",
                    duration=0.0,
                    validation_type="check_script",
                    details={
                        "skipped": True,
                        "reason": "Remote targets don't support localhost-based check scripts",
                    },
                )
            )
            return None

        check_start = time.time()
        check_result = session.run_check_script_detailed()
        validation_results.append(
            ValidationResult(
                passed=check_result["passed"],
                message=check_result["message"],
                duration=time.time() - check_start,
                validation_type="check_script",
                details=check_result.get("details"),
            )
        )
        if not check_result["passed"]:
            return check_result["message"]
        return None

    def _run_deploy_and_verify(
        self,
        test: TestDefinition,
        session: DeploymentSession,
        start_time: float,
        validation_results: list[ValidationResult],
    ) -> tuple[str, str | None]:
        """Run deployment and verification, return (deploy_logs, error or None)."""
        session.prepare()

        if not session.deploy():
            deploy_logs = session._last_deploy_error or "Deployment failed"
            return deploy_logs, f"Deploy failed: {deploy_logs}"

        deploy_duration = time.time() - start_time
        deploy_logs = f"Deployed {session.app_name} in {deploy_duration:.1f}s"
        validation_results.append(
            ValidationResult(
                passed=True,
                message=f"Deployed {session.app_name} ({deploy_duration:.1f}s)",
                duration=deploy_duration,
                validation_type="deploy",
                details={"app_name": session.app_name},
            )
        )

        if not session.check_deployed():
            return deploy_logs, "App not found in deployment list after deploy"

        validation_results.append(
            ValidationResult(
                passed=True,
                message=f"Found {session.app_name} in app list",
                duration=0.0,
                validation_type="deploy_check",
            )
        )

        return deploy_logs, None

    def _validate_app_path(
        self, test: TestDefinition, start_time: float
    ) -> TestResult | None:
        """Validate app path exists. Returns TestResult on error, None if OK."""
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
        return None

    def run(self, test: TestDefinition) -> TestResult:
        """Run a deployment test.

        Args:
            test: The test definition to run

        Returns:
            TestResult with all validation results
        """
        start_time = time.time()
        validation_results: list[ValidationResult] = []
        deploy_logs = ""
        error = None

        if path_error := self._validate_app_path(test, start_time):
            return path_error

        app_source = self._create_app_source(test)
        if self.verbose:
            print(f"  Deploying {test.name} from {test.app_path}...")

        session = DeploymentSession(
            app=app_source,
            target=self.target,
            config={"verbose": self.verbose, "debug": self.verbose},
        )

        try:
            deploy_logs, error = self._run_deploy_and_verify(
                test, session, start_time, validation_results
            )
            if error:
                return TestResult(
                    test=test,
                    passed=False,
                    deploy_logs=deploy_logs,
                    validation_results=validation_results,
                    total_duration=time.time() - start_time,
                    error=error,
                )

            if app_source.has_procfile:
                if http_error := self._run_http_test(session, validation_results):
                    return TestResult(
                        test=test,
                        passed=False,
                        validation_results=validation_results,
                        total_duration=time.time() - start_time,
                        error=http_error,
                    )

            if app_source.has_check_script:
                if check_error := self._run_check_script(session, validation_results):
                    return TestResult(
                        test=test,
                        passed=False,
                        validation_results=validation_results,
                        total_duration=time.time() - start_time,
                        error=check_error,
                    )

        except Exception as e:
            error = str(e)
            if self.verbose:
                traceback.print_exc()

        finally:
            if self.cleanup and self.verbose:
                print(f"  Cleaning up {test.name}...")
            if self.cleanup:
                session.cleanup()

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
