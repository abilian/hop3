# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Verification utilities for deployed applications.

This module handles verifying deployed applications:
- HTTP endpoint testing
- Check script execution
- Response validation
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from hop3_testing.util.console import Console, PrintingConsole

if TYPE_CHECKING:
    from hop3_testing.targets.base import TargetInfo

    from .catalog import AppSource


@dataclass(frozen=True)
class HttpVerifier:
    """Verifies HTTP endpoints of deployed applications."""

    target_info: TargetInfo
    """Target connection info."""

    app_name: str
    """Name of the deployed app."""

    console: Console = field(default_factory=PrintingConsole)
    """Console for output."""

    def test(
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int = HTTPStatus.OK,
        max_retries: int = 20,
    ) -> bool:
        """Test HTTP access to the deployed app.

        Args:
            hostname: Virtual host name (default: {app_name}.test.local)
            path: URL path to test
            expected_status: Expected HTTP status code
            max_retries: Maximum number of retry attempts

        Returns:
            True if test passed, False otherwise
        """
        result = self.test_detailed(hostname, path, expected_status, max_retries)
        return result["passed"]

    def test_detailed(
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int = HTTPStatus.OK,
        max_retries: int = 20,
    ) -> dict[str, Any]:
        """Test HTTP access and return detailed results.

        Returns:
            Dict with: passed, message, details (url, status, body preview, etc.)
        """
        result: dict[str, Any] = {"passed": False, "message": "", "details": {}}

        if hostname is None:
            hostname = f"{self.app_name}.test.local"

        url = self._build_url(path)
        result["details"]["url"] = url
        result["details"]["hostname"] = hostname
        result["details"]["expected_status"] = expected_status

        self.console.info(f"Testing HTTP: {url} (Host: {hostname})")

        for attempt in range(max_retries):
            try:
                response = httpx.get(
                    url,
                    headers={"Host": hostname},
                    timeout=2.0,
                    follow_redirects=True,
                )

                result["details"]["status_code"] = response.status_code
                result["details"]["attempts"] = attempt + 1

                # Capture body preview
                body = response.text[:500] if response.text else ""
                result["details"]["body_preview"] = body

                if response.status_code == expected_status:
                    result["passed"] = True
                    result["message"] = f"HTTP {response.status_code} from {url}"
                    self.console.success(
                        f"HTTP test passed (status: {response.status_code})"
                    )
                    return result

                if response.status_code == HTTPStatus.BAD_GATEWAY:
                    self.console.debug(
                        f"Attempt {attempt + 1}/{max_retries}: "
                        "Backend not ready, retrying..."
                    )
                    time.sleep(0.5)
                    continue

                result["message"] = (
                    f"HTTP {response.status_code} (expected {expected_status})"
                )
                self.console.debug(f"Unexpected status code: {response.status_code}")
                return result

            except (httpx.HTTPError, httpx.ConnectError) as e:
                result["details"]["last_error"] = str(e)
                self.console.debug(f"Attempt {attempt + 1}/{max_retries}: {e}")
                time.sleep(0.5)

        result["message"] = f"HTTP test failed after {max_retries} attempts"
        self.console.error(f"HTTP test failed after {max_retries} attempts")
        return result

    def _build_url(self, path: str) -> str:
        """Build the full URL for testing."""
        http_base = self.target_info.http_base.rstrip("/")
        return f"{http_base}{path}"


@dataclass(frozen=True)
class CheckScriptRunner:
    """Runs check.py scripts for deployed applications."""

    target_info: TargetInfo
    """Target connection info."""

    app: AppSource
    """Application source with check script."""

    app_name: str
    """Name of the deployed app."""

    console: Console = field(default_factory=PrintingConsole)
    """Console for output."""

    def run(self) -> bool:
        """Run the check script.

        Returns:
            True if check passed or no script exists, False otherwise
        """
        result = self.run_detailed()
        return result["passed"]

    def run_detailed(self) -> dict[str, Any]:
        """Run check script and return detailed results.

        Returns:
            Dict with: passed, message, details
        """
        result: dict[str, Any] = {"passed": False, "message": "", "details": {}}

        if not self.app.has_check_script:
            result["passed"] = True
            result["message"] = "No check script (skipped)"
            self.console.info("No check script available")
            return result

        try:
            hostname, http_port = self._get_connection_info()
            check_script_path = self.app.path / "check.py"

            result["details"]["script"] = str(check_script_path)
            result["details"]["hostname"] = hostname
            result["details"]["port"] = http_port

            # Execute check script
            ctx: dict[str, Any] = {}
            exec(check_script_path.read_text(), ctx)  # noqa: S102

            if "check" not in ctx:
                result["message"] = "check() function not found in check.py"
                self.console.warning("check() function not found in check.py")
                return result

            ctx["check"](hostname, http_port)
            result["passed"] = True
            result["message"] = f"check.py passed ({check_script_path.name})"
            self.console.success("Check script passed")
            return result

        except AssertionError as e:
            result["message"] = f"Assertion failed: {e}"
            result["details"]["error_type"] = "AssertionError"
            result["details"]["error"] = str(e)
            self.console.error(f"Check script failed: {e}")
            return result

        except Exception as e:
            result["message"] = f"Check script error: {e}"
            result["details"]["error_type"] = type(e).__name__
            result["details"]["error"] = str(e)
            self.console.error(f"Check script failed: {e}")
            return result

    def _get_connection_info(self) -> tuple[str, int]:
        """Get hostname and port for check script.

        Returns:
            Tuple of (hostname, port)
        """
        http_base = self.target_info.http_base
        parsed = urlparse(http_base)

        if parsed.hostname == "localhost":
            # Local Docker target - use app-specific hostname
            hostname = f"{self.app_name}.test.local"
            http_port = parsed.port or 80
        else:
            # Remote target - use the actual remote hostname
            hostname = parsed.hostname or "localhost"
            http_port = parsed.port or 80

        return hostname, http_port


@dataclass
class AppVerifier:
    """Combined verifier for deployed applications.

    Convenience class that combines HTTP verification and check script
    execution for a deployed app.
    """

    target_info: TargetInfo
    """Target connection info."""

    app: AppSource
    """Application source."""

    app_name: str
    """Name of the deployed app."""

    console: Console = field(default_factory=PrintingConsole)
    """Console for output."""

    http_verifier: HttpVerifier = field(init=False)
    """HTTP verifier instance."""

    check_runner: CheckScriptRunner = field(init=False)
    """Check script runner instance."""

    def __post_init__(self) -> None:
        """Initialize sub-verifiers."""
        self.http_verifier = HttpVerifier(self.target_info, self.app_name, self.console)
        self.check_runner = CheckScriptRunner(
            self.target_info, self.app, self.app_name, self.console
        )

    def verify_http(
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int = HTTPStatus.OK,
        max_retries: int = 20,
    ) -> bool:
        """Verify HTTP endpoint."""
        return self.http_verifier.test(hostname, path, expected_status, max_retries)

    def verify_http_detailed(
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int = HTTPStatus.OK,
        max_retries: int = 20,
    ) -> dict[str, Any]:
        """Verify HTTP endpoint with detailed results."""
        return self.http_verifier.test_detailed(
            hostname, path, expected_status, max_retries
        )

    def run_check_script(self) -> bool:
        """Run check script if present."""
        return self.check_runner.run()

    def run_check_script_detailed(self) -> dict[str, Any]:
        """Run check script with detailed results."""
        return self.check_runner.run_detailed()

    def verify_all(
        self,
        http_path: str = "/",
        expected_status: int = HTTPStatus.OK,
    ) -> tuple[bool, str]:
        """Run all verifications.

        Returns:
            Tuple of (all_passed, failure_message)
        """
        # HTTP test (if app has web interface)
        if self.app.has_procfile:
            if not self.verify_http(path=http_path, expected_status=expected_status):
                return False, "HTTP verification failed"

        # Check script
        if self.app.has_check_script:
            if not self.run_check_script():
                return False, "Check script failed"

        return True, ""
