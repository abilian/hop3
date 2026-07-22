# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deployment test runner."""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from hop3_testing.apps.catalog import AppSource
from hop3_testing.apps.deployment import BODY_FETCH_LIMIT, DeploymentSession
from hop3_testing.bundle import collect_diagnostic_bundle
from hop3_testing.exceptions import (
    DeploymentError,
    DeployTimeoutError,
    TargetOutOfDiskError,
)
from hop3_testing.runtime_diagnostics import collect_runtime_logs
from hop3_testing.util.console import PrintingConsole, Verbosity

from .base import TestResult, ValidationResult

if TYPE_CHECKING:
    from hop3_testing.bundle import Bundle
    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.targets.base import DeploymentTarget


# The hop3-server venv Python. hop3-server depends on httpx (pyproject), so this
# interpreter is guaranteed present and can run any check.py that imports httpx —
# no `uv`, no `--with httpx`, no reliance on ~/.local/bin being on a non-login
# SSH PATH (which it isn't). VENV_DIR = /home/hop3/venv (installer constants),
# and the harness hardcodes /home/hop3 throughout.
_HOP3_VENV_PYTHON = "/home/hop3/venv/bin/python3"


def _target_kind(target: DeploymentTarget) -> str:
    """Map a target to the bundle's ``target_kind`` ("docker"/"ssh"/"hetzner")."""
    name = type(target).__name__
    if "Remote" in name:
        return "ssh"
    return "docker"


def _collect_runtime_logs(target: DeploymentTarget, app_name: str | None) -> str:
    """Best-effort app-side runtime logs (gunicorn/app stderr, migrate
    output, docker logs) captured before cleanup. Never raises — diagnostics
    must not crash the run. Module-level so tests can patch the binding."""
    try:
        return collect_runtime_logs(target, app_name)
    except Exception:
        return ""


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

    console: PrintingConsole = field(default_factory=PrintingConsole)
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
        """Run HTTP validations from test.toml, or default for Procfile apps.

        A passing HTTP check MUST assert app-specific body content, not just a
        status code — otherwise an app goes green on a bare 200: a placeholder /
        install-wizard page, a 200-rendered error page, or (via a Host mismatch)
        another app's default_server content. So at least one validation must
        carry a `contains`, OR the app must ship a check.py (which asserts
        content and now runs on remote too). An app with neither fails loud
        rather than passing on the wrong thing (audit C8).
        """
        http_validations = [v for v in test.validations if v.type == "http"]

        if http_validations:
            if not any(v.expect.contains for v in http_validations) and (
                not app_source.has_check_script
            ):
                return self._fail_no_body_assertion(
                    test,
                    validation_results,
                    "HTTP validation asserts only a status code",
                )
            for v in http_validations:
                path = v.path or "/"
                # Prefer status_in (list) over status (int) when both are
                # declared; status_in=[200, 202] lets xwiki's first-boot
                # wizard (returns 202) match without accepting anything else.
                expected_status: int | list[int] = (
                    v.expect.status_in
                    if v.expect.status_in is not None
                    else (v.expect.status or 200)
                )
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
            if not app_source.has_check_script:
                return self._fail_no_body_assertion(
                    test,
                    validation_results,
                    "Procfile app declares no [[validations]]",
                )
            return self._run_http_test(session, validation_results)

        return None

    def _fail_no_body_assertion(
        self,
        test: TestDefinition,
        validation_results: list[ValidationResult],
        reason: str,
    ) -> str:
        """Record a loud failure: the app asserts no body content (audit C8)."""
        msg = (
            f"{test.name}: {reason} and the app has no check.py — a bare-status "
            "pass is not allowed. Add a body assertion (`contains` on a "
            "[[test.validations]] entry or `[healthcheck].contains`), or a "
            "check.py, so a green test proves the app served its own content."
        )
        validation_results.append(
            ValidationResult(
                passed=False,
                message=msg,
                duration=0.0,
                validation_type="http",
            )
        )
        return msg

    def _run_http_validation(
        self,
        session: DeploymentSession,
        path: str,
        expected_status: int | list[int],
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
            actual = http_result.get("details", {}).get("status_code", "?")
            if contains not in body:
                # Show the whole checked body (not a 200-char stub): a `contains`
                # miss is undiagnosable without seeing where the marker should be.
                shown = body if len(body) <= 8000 else body[:8000] + "…[truncated]"
                # If the fetch hit its limit, "does not contain" is not a sound
                # conclusion — the marker may sit beyond the bytes we looked at.
                # Say so rather than report a possible false negative as fact.
                caveat = (
                    f" WARNING: the body hit the {BODY_FETCH_LIMIT}-char fetch "
                    "limit, so the marker may exist beyond the bytes checked; "
                    "this may be a false negative."
                    if len(body) >= BODY_FETCH_LIMIT
                    else ""
                )
                http_result["passed"] = False
                http_result["message"] = (
                    f"HTTP {actual} OK but body does not contain '{contains}' "
                    f"(checked {len(body)} chars of the response).{caveat}\n{shown}"
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

        check_start = time.time()
        if is_remote_target:
            # Was: silently fabricated passed=True. check.py asserts app-specific
            # body content, so skipping it on remote meant the ONLY assertion
            # that distinguishes the app from a bare 200 never ran. Run it ON the
            # server instead (where localhost is the app's nginx), and never pass
            # when it can't run (audit C8).
            check_result = self._run_check_script_remote(session)
        else:
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

    def _run_check_script_remote(self, session: DeploymentSession) -> dict[str, Any]:
        """Execute check.py ON the remote server (where localhost == nginx).

        The local runner can't run check.py against a remote box: check.py hits
        ``http://localhost:{port}`` with a Host header, and on the test client
        ``localhost`` is the client, not the server. So upload the script and run
        it on the server, where ``localhost:80`` is the app's nginx and the Host
        header selects the app vhost. NEVER silently passes: a server that cannot
        run check.py is a hard FAIL (audit C8).
        """
        host = session.test_hostname
        check_path = session.app.path / "check.py"
        remote_path = f"/tmp/hop3-check-{session.app_name}.py"
        try:
            self.target.upload_file(check_path, remote_path)
            # Run with the hop3-server venv Python (has httpx). Bare `uv` isn't on
            # the non-login SSH PATH (exit 127); this interpreter always is.
            exit_code, stdout, stderr = self.target.exec_run(
                f"{_HOP3_VENV_PYTHON} {remote_path} {host} 80"
            )
        except Exception as e:  # upload/exec failed -> fail loud, never pass
            return {
                "passed": False,
                "message": f"check.py could not run on remote server: {e}",
                "details": {"remote": True, "script": str(check_path)},
            }
        passed = exit_code == 0
        message = (
            f"check.py passed on server (Host: {host})"
            if passed
            else f"check.py FAILED on server (exit {exit_code}): "
            f"{(stderr or stdout)[:300]}"
        )
        return {
            "passed": passed,
            "message": message,
            "details": {
                "remote": True,
                "script": str(check_path),
                "host": host,
                "exit_code": exit_code,
            },
        }

    # Single generous deploy timeout. Matches the server-side build
    # timeout (see hop3/plugins/docker/builder.py::BUILD_TIMEOUT_SECONDS);
    # anything above 30 min is a design smell, not a tier problem.
    _DEPLOY_TIMEOUT_SECONDS = 30 * 60

    def _run_deploy_and_verify(
        self,
        test: TestDefinition,
        session: DeploymentSession,
        start_time: float,
        validation_results: list[ValidationResult],
    ) -> tuple[str, str | None, bool]:
        """Run deployment and verification.

        Returns ``(deploy_logs, error or None, infra_failed)``. ``infra_failed``
        is True for the two UNAMBIGUOUS infrastructure failures — target out of
        disk and deploy timeout — which are hard-failed regardless of
        ``expects_failure`` so they can't invert into a green negative test
        (audit C7). A genuine builder/deployer rejection stays ``infra_failed``
        False and may still satisfy an ``expects-failure`` test.

        ponytail: a server-unreachable deploy (a non-zero CLI exit that isn't a
        builder rejection) is NOT yet classified as infra, so it can still turn
        a negative test green — that carve-out needs the CLI to reliably emit
        ExitCode.DEPLOYMENT_ERROR (8) for builder rejections vs NETWORK_ERROR (7)
        for outages, which isn't validated. Disk + timeout are the cases the
        audit names; add the exit-code carve-out once rejections are confirmed
        to exit 8.
        """
        # Reclaim disk before deploying so a full target fails with one clear
        # message instead of cascading misleading ENOSPC per-app errors.
        try:
            self.target.ensure_disk_headroom()
        except TargetOutOfDiskError as e:
            return "", str(e), True

        session.prepare()

        try:
            session.deploy(deploy_timeout=self._DEPLOY_TIMEOUT_SECONDS)
        except DeployTimeoutError as e:
            # Hung deploy = infra. Never satisfies a negative test. (Subclass of
            # DeploymentError, so this except MUST precede the base one below.)
            # Persist the FULL transcript (1st return → bundle/DB); the console
            # message (2nd return) keeps the truncated head+tail. Otherwise the
            # root error is lost whenever it isn't in the last 2000 chars.
            shown = session.last_deploy_error or str(e)
            full = session.last_deploy_output or shown
            return full, f"Deploy failed: {shown}", True
        except DeploymentError as e:
            shown = session.last_deploy_error or str(e)
            full = session.last_deploy_output or shown
            return full, f"Deploy failed: {shown}", False

        deploy_duration = time.time() - start_time
        # Keep the FULL deploy output (always), prefixed with the timing summary.
        full_output = session.last_deploy_output or ""
        deploy_logs = (
            f"Deployed {session.app_name} in {deploy_duration:.1f}s\n{full_output}"
        ).rstrip()
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
                False,
            )

        validation_results.append(
            ValidationResult(
                passed=True,
                message=f"Found {session.app_name} in app list",
                duration=0.0,
                validation_type="deploy_check",
            )
        )

        return deploy_logs, None, False

    def _handle_expects_failure(
        self,
        *,
        test: TestDefinition,
        session: DeploymentSession,
        start_time: float,
        deploy_logs: str,
        deploy_failed: bool,
        validation_results: list[ValidationResult],
    ) -> TestResult:
        """Invert deploy success/failure for negative test cases.

        A deploy failure → PASS (with a synthetic validation result so
        the report shows the inversion explicitly). A deploy success →
        FAIL (unexpected pass — the app should have been rejected).

        Cleanup runs in both cases but is isolated in its own
        try/except — a CleanupError here must NOT flip the test
        result back to failed (mirrors the happy-path cleanup in
        `run()`, which also ignores cleanup errors).
        """
        if deploy_failed:
            # Visible trace for debugging: this line shows up in the
            # per-test log so operators can tell at a glance whether
            # the inversion actually fired.
            self.console.info(
                f"expects-failure=true: inverting deploy failure → PASS for {test.name}"
            )
            validation_results.append(
                ValidationResult(
                    passed=True,
                    message="Deploy failed as expected (expects-failure=true)",
                    duration=time.time() - start_time,
                    validation_type="expects_failure",
                )
            )
            self._safe_cleanup(test, session)
            return TestResult(
                test=test,
                passed=True,
                validation_results=validation_results,
                deploy_logs=deploy_logs,
                total_duration=time.time() - start_time,
                deployed_app_name=session.app_name,
            )

        # Unexpected success — the deploy went through on an app that
        # was supposed to be rejected. That's a regression: either the
        # rejection path broke, or the test is mislabeled.
        err = (
            "Unexpected deploy success: expects-failure=true but the "
            "deployment succeeded. Either the rejection path has "
            "regressed, or the test should drop expects-failure."
        )
        runtime_logs = _collect_runtime_logs(self.target, session.app_name)
        bundle = self._collect_bundle(session, deploy_logs)
        self._safe_cleanup(test, session)
        return TestResult(
            test=test,
            passed=False,
            validation_results=validation_results,
            deploy_logs=deploy_logs,
            total_duration=time.time() - start_time,
            error=err,
            deployed_app_name=session.app_name,
            runtime_logs=runtime_logs,
            bundle=bundle,
        )

    def _collect_bundle(
        self, session: DeploymentSession, deploy_logs: str = ""
    ) -> Bundle:
        """Collect the unified diagnostic bundle from the target before cleanup."""
        try:
            expected_port = session.get_app_port()
        except Exception:  # diagnostics must never crash the run
            expected_port = None
        # _collect_bundle is only ever called on a failed test, so force the
        # bundle to disk even when the runtime classifier says "ok" — a check.py
        # / HTTP-`contains` failure serves fine yet still needs a replayable
        # bundle for `hop3-test why`.
        bundle = collect_diagnostic_bundle(
            self.target,
            session.app_name,
            deploy_logs=deploy_logs,
            expected_port=expected_port,
            target_kind=_target_kind(self.target),
            force_persist=True,
        )
        # Point the developer at the durable copy NOW, at the failure. The app
        # is torn down next (_safe_cleanup), so the deploy transcript's own
        # `hop3 app logs --app <app> --build` pointer is already dead here — the
        # bundle is where every section (build, deploy, journal, nginx, …) lives.
        # Use warning (not info): info is verbose-only, so on a normal run the
        # one pointer to the surviving logs was invisible.
        if bundle.artifact_dir:
            self.console.warning(
                f"Full local diagnostics (survive teardown): {bundle.artifact_dir}"
                f"  |  replay: {bundle.why}"
            )
        else:
            self.console.warning(f"Full logs recorded → {bundle.why}")
        return bundle

    def _safe_cleanup(self, test: TestDefinition, session: DeploymentSession) -> None:
        """Run cleanup but swallow any error.

        A failed cleanup is interesting for debugging but must NOT
        flip a computed test result. The main run() path already
        behaves this way by placing cleanup outside its try/except;
        this helper extends the same contract to the expects_failure
        branch.
        """
        if not self.cleanup:
            return
        self.console.info(f"Cleaning up {test.name}...")
        try:
            session.cleanup()
        except Exception as exc:
            # Surfaced (not swallowed): a failed cleanup leaks resources and
            # is the leading cause of later cascade failures — make it visible.
            self.console.warning(
                f"Cleanup FAILED for {test.name} — resources may leak "
                f"(addons/disk): {exc}"
            )

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

    def run(self, test: TestDefinition) -> TestResult:  # noqa: PLR0911 — one return per distinct deploy/validation outcome (infra fail, expects-failure, deploy error, http error, check error, success); coalescing would obscure them
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
            """Build a failure TestResult, then tear the app down.

            Captures runtime logs and the diagnostic bundle from the target
            while the app is still present, THEN runs cleanup — so a failed test
            never leaks its app (and its fixed-port claim, addon slots, …) into
            the next deploy. Previously these early-return paths skipped cleanup
            entirely; only the success path tore down.
            """
            result = TestResult(
                test=test,
                passed=False,
                deploy_logs=deploy_logs,
                validation_results=validation_results,
                total_duration=time.time() - start_time,
                error=err,
                deployed_app_name=session.app_name,
                runtime_logs=_collect_runtime_logs(self.target, session.app_name),
                bundle=self._collect_bundle(session, deploy_logs),
            )
            self._safe_cleanup(test, session)
            return result

        try:
            deploy_logs, error, infra_failed = self._run_deploy_and_verify(
                test, session, start_time, validation_results
            )
            # Infrastructure failures (target out of disk, hung deploy timeout)
            # are HARD fails regardless of expects_failure — they must never
            # invert into a green negative test and mask a total outage (C7).
            if infra_failed:
                # _run_deploy_and_verify always pairs infra_failed with a
                # non-None message (disk-full / deploy-timeout); narrow for it.
                assert error is not None, "infra_failed implies a failure message"
                return _fail_result(error, deploy_logs=deploy_logs)
            # Negative test cases: a genuine builder/deployer REJECTION is the
            # expected outcome (e.g., an input the builder is expected to
            # reject — see apps/bad/). We record a PASS, skip the
            # HTTP/check-script stages (there's no running app to probe), and
            # short-circuit to cleanup.
            if test.expects_failure:
                return self._handle_expects_failure(
                    test=test,
                    session=session,
                    start_time=start_time,
                    deploy_logs=deploy_logs,
                    deploy_failed=error is not None,
                    validation_results=validation_results,
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

        bundle = None
        runtime_logs = ""
        if not passed:
            runtime_logs = _collect_runtime_logs(self.target, session.app_name)
            bundle = self._collect_bundle(session, deploy_logs)

        # Cleanup AFTER collecting diagnostics so the app dir and docker
        # containers are still around. Routed through _safe_cleanup so a
        # cleanup failure is surfaced (not silent) and never crashes the run.
        self._safe_cleanup(test, session)

        return TestResult(
            test=test,
            passed=passed,
            validation_results=validation_results,
            deploy_logs=deploy_logs,
            total_duration=time.time() - start_time,
            error=error,
            deployed_app_name=session.app_name,
            runtime_logs=runtime_logs,
            bundle=bundle,
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
