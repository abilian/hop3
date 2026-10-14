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

from hop3_testing.util.console import PrintingConsole

if TYPE_CHECKING:
    from collections.abc import Iterable

    from hop3_testing.targets.base import TargetInfo

    from .catalog import AppSource


def _status_match(actual: int, expected: int | Iterable[int]) -> bool:
    """Whether ``actual`` satisfies ``expected`` (scalar or any-of)."""
    if isinstance(expected, int):
        return actual == expected
    return actual in set(expected)


def _format_expected(expected: int | Iterable[int]) -> str:
    """Human-readable rendering of an expected-status spec."""
    if isinstance(expected, int):
        return str(expected)
    codes = sorted(set(expected))
    if len(codes) == 1:
        return str(codes[0])
    if len(codes) == 2:
        return f"{codes[0]} or {codes[1]}"
    return ", ".join(str(c) for c in codes[:-1]) + f", or {codes[-1]}"


@dataclass(frozen=True)
class HttpVerifier:
    """Verifies HTTP endpoints of deployed applications."""

    target_info: TargetInfo
    """Target connection info."""

    app_name: str
    """Name of the deployed app."""

    console: PrintingConsole = field(default_factory=PrintingConsole)
    """Console for output."""

    def test(
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int | Iterable[int] = HTTPStatus.OK,
        max_retries: int = 20,
    ) -> bool:
        """Test HTTP access to the deployed app.

        Args:
            hostname: Virtual host name (default: {app_name}.test.local)
            path: URL path to test
            expected_status: Expected HTTP status code, or an iterable of
                accepted codes (for apps whose first-boot install wizard
                legitimately returns 202, etc.)
            max_retries: Maximum number of retry attempts

        Returns:
            True if test passed, False otherwise
        """
        result = self.test_detailed(hostname, path, expected_status, max_retries)
        return result["passed"]

    def test_detailed(  # noqa: PLR0915
        self,
        hostname: str | None = None,
        path: str = "/",
        expected_status: int | Iterable[int] = HTTPStatus.OK,
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
                # First check for redirects without following them
                initial_response = httpx.get(
                    url,
                    headers={"Host": hostname},
                    timeout=2.0,
                    follow_redirects=False,
                    verify=False,  # ken: self-signed per-host cert, and never leaves loopback
                )

                # Log redirect info if we got a 3xx
                if 300 <= initial_response.status_code < 400:
                    location = initial_response.headers.get("location", "")
                    self.console.debug(
                        f"Redirect detected: {initial_response.status_code} -> {location}"
                    )
                    result["details"]["redirect_status"] = initial_response.status_code
                    result["details"]["redirect_location"] = location

                    # If redirect is to a hostname we can't resolve, fail early
                    if ".test.local" in location or ".local" in location:
                        result["message"] = (
                            f"Redirect to unresolvable hostname: {location}"
                        )
                        self.console.error(
                            f"Server returned redirect to unresolvable URL: {location}"
                        )
                        return result

                # Now make the actual request following redirects
                response = httpx.get(
                    url,
                    headers={"Host": hostname},
                    timeout=2.0,
                    follow_redirects=True,
                    verify=False,  # ken: self-signed per-host cert, and never leaves loopback
                )

                result["details"]["status_code"] = response.status_code
                result["details"]["attempts"] = attempt + 1

                # Capture body preview. 4096 chars is enough for most HTML
                # pages and lets `contains` checks see beyond the head/header.
                body = response.text[:4096] if response.text else ""
                result["details"]["body_preview"] = body

                if _status_match(response.status_code, expected_status):
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
                    f"HTTP {response.status_code} "
                    f"(expected {_format_expected(expected_status)})"
                )
                self.console.debug(f"Unexpected status code: {response.status_code}")
                return result

            except (httpx.HTTPError, httpx.ConnectError) as e:
                result["details"]["last_error"] = str(e)
                self.console.debug(f"Attempt {attempt + 1}/{max_retries}: {e}")
                time.sleep(0.5)

        # Build detailed error message
        details = result["details"]
        error_parts = [f"HTTP test failed after {max_retries} attempts"]
        error_parts.append(f"URL: {details.get('url', 'unknown')}")
        error_parts.append(f"Host header: {details.get('hostname', 'unknown')}")
        if "status_code" in details:
            error_parts.append(f"Last status: {details['status_code']}")
        if "last_error" in details:
            error_parts.append(f"Last error: {details['last_error']}")
        if details.get("body_preview"):
            body = details["body_preview"][:200]
            error_parts.append(f"Response body: {body}")

        result["message"] = " | ".join(error_parts)
        self.console.error("\n".join(error_parts))
        return result

    def _build_url(self, path: str) -> str:
        """
        The URL to test, over TLS.

        This route is the fallback for an app with no direct port — a static
        site, served by nginx itself. Its sibling exists (as its docstring says)
        "to avoid hostname resolution and SSL redirect issues", and this one had
        neither defence: Hop3 redirects HTTP to HTTPS, so a plain-HTTP request
        here got a 301 and the check reported it as the app's status. Going to
        the TLS port is what the redirect was asking for.
        """
        if not self.target_info.https_base:
            msg = "The target publishes no HTTPS port, and Hop3 serves apps over TLS"
            raise RuntimeError(msg)
        return f"{self.target_info.https_base}{path}"
