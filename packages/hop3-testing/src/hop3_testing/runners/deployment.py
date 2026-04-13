# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deployment test runner."""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from hop3_testing.apps.catalog import AppSource
from hop3_testing.apps.deployment import DeploymentSession
from hop3_testing.exceptions import DeploymentError
from hop3_testing.runtime_diagnostics import (
    collect_runtime_logs as _collect_runtime_logs,
)
from hop3_testing.util.console import Console, PrintingConsole, Verbosity

from .base import TestResult, ValidationResult

if TYPE_CHECKING:
    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.targets.base import DeploymentTarget


@dataclass(frozen=True)
class DeploymentTestRunner:
    """Runs deployment tests using the existing DeploymentSession.

    A deployment test consists of:
    1. Deploy the application to the target via DeploymentSession
    2. Wait for the app to be running
    3. Run HTTP test and check script (via DeploymentSession)
    4. Run additional validations from test.toml
    5. Cleanup (destroy the app)
    """

    target: DeploymentTarget
    """The deployment target to run tests on."""

    cleanup: bool = True
    """Whether to destroy apps after testing."""

    verbose: bool = False
    """Whether to print verbose output."""

    console: Console = field(default_factory=PrintingConsole)
    """Console for output."""

    def __post_init__(self) -> None:
        """Set verbosity after initialization."""
        if self.verbose:
            self.console.set_verbosity(Verbosity.VERBOSE)

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

    def _run_http_validations(
        self,
        test: TestDefinition,
        session: DeploymentSession,
        app_source: AppSource,
        validation_results: list[ValidationResult],
    ) -> str | None:
        """Run HTTP validations from test.toml, or default for Procfile apps."""
        http_validations = [v for v in test.validations if v.type == "http"]

        if http_validations:
            for v in http_validations:
                path = v.path or "/"
                expected_status = v.expect.status or 200
                contains = v.expect.contains
                if error := self._run_http_validation(
                    session,
                    path,
                    expected_status,
                    contains,
                    validation_results,
                ):
                    return error
        elif app_source.has_procfile:
            # Legacy: no [[validations]] in test.toml, default check
            return self._run_http_test(session, validation_results)

        return None

    def _run_http_validation(
        self,
        session: DeploymentSession,
        path: str,
        expected_status: int,
        contains: str | None,
        validation_results: list[ValidationResult],
    ) -> str | None:
        """Run an HTTP validation from test.toml and return error or None."""
        http_start = time.time()
        http_result = session.test_http_detailed(
            path=path,
            expected_status=expected_status,
        )
        duration = time.time() - http_start

        # Check contains if specified and HTTP status matched
        if http_result["passed"] and contains:
            body = http_result.get("details", {}).get("body_preview", "")
            if contains not in body:
                http_result["passed"] = False
                http_result["message"] = (
                    f"HTTP {expected_status} OK but body does not contain "
                    f"'{contains}'. Got: {body[:200]}"
                )

        validation_results.append(
            ValidationResult(
                passed=http_result["passed"],
                message=http_result["message"],
                duration=duration,
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

    def _deploy_timeout_for(self, test: TestDefinition) -> int:
        """Pick a deploy timeout based on the test's tier.

        Heavy Docker builds (e.g., Monica building Laravel+npm assets)
        routinely need more than the 10-min default. Nix apps that
        pull from binary cache are fast on cache hit but slow on
        miss. The tier expresses the expectation up-front.
        """
        from hop3_testing.catalog.models import Tier  # noqa: PLC0415

        tier_to_seconds = {
            Tier.FAST: 300,  # 5 min
            Tier.MEDIUM: 600,  # 10 min
            Tier.SLOW: 1200,  # 20 min
            Tier.VERY_SLOW: 1800,  # 30 min
        }
        return tier_to_seconds.get(test.tier, 600)

    def _run_deploy_and_verify(
        self,
        test: TestDefinition,
        session: DeploymentSession,
        start_time: float,
        validation_results: list[ValidationResult],
    ) -> tuple[str, str | None]:
        """Run deployment and verification, return (deploy_logs, error or None)."""
        session.prepare()

        try:
            session.deploy(deploy_timeout=self._deploy_timeout_for(test))
        except DeploymentError as e:
            deploy_logs = session.last_deploy_error or str(e)
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
            check_output = session.last_check_output or "(no output captured)"
            return (
                deploy_logs,
                f"App not found in deployment list after deploy.\nhop3 apps output: {check_output}",
            )

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
        self.console.info(f"Deploying {test.name} from {test.app_path}...")

        session = DeploymentSession(
            app=app_source,
            target=self.target,
            config={"verbose": self.verbose, "debug": self.verbose},
            console=self.console,
        )

        def _fail_result(
            err: str,
            *,
            deploy_logs: str = "",
        ) -> TestResult:
            """Build a failure TestResult, capturing runtime logs
            from the target BEFORE ``finally:`` cleanup runs — so
            containers and app dirs are still present."""
            return TestResult(
                test=test,
                passed=False,
                deploy_logs=deploy_logs,
                validation_results=validation_results,
                total_duration=time.time() - start_time,
                error=err,
                deployed_app_name=session.app_name,
                runtime_logs=_collect_runtime_logs(self.target, session.app_name),
            )

        try:
            deploy_logs, error = self._run_deploy_and_verify(
                test, session, start_time, validation_results
            )
            if error:
                return _fail_result(error, deploy_logs=deploy_logs)

            if http_error := self._run_http_validations(
                test, session, app_source, validation_results
            ):
                return _fail_result(http_error)

            if app_source.has_check_script:
                if check_error := self._run_check_script(session, validation_results):
                    return _fail_result(check_error)

        except Exception as e:
            error = str(e)
            self.console.debug(traceback.format_exc())

        passed = error is None and all(v.passed for v in validation_results)

        runtime_logs = ""
        if not passed:
            runtime_logs = _collect_runtime_logs(self.target, session.app_name)

        # Cleanup AFTER collecting runtime diagnostics so the app
        # dir and docker containers are still around.
        if self.cleanup:
            self.console.info(f"Cleaning up {test.name}...")
            session.cleanup()

        return TestResult(
            test=test,
            passed=passed,
            validation_results=validation_results,
            deploy_logs=deploy_logs,
            total_duration=time.time() - start_time,
            error=error,
            deployed_app_name=session.app_name,
            runtime_logs=runtime_logs,
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
            name=test.deploy_name,
            path=app_path,
            category=category,
            description=test.description or "",
        )
