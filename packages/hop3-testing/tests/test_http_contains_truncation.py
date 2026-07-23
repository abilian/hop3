# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
A `contains` miss on a truncated body must not be reported as settled fact.

The body is fetched with ``curl … | head -c BODY_FETCH_LIMIT`` and the assertion
is matched against *that*. At the previous 16 KB limit, WordPress 6.4's block
theme inlined enough CSS into ``<head>`` to push the asserted post title past the
window, so the 2026-07-21 matrix run reported "body does not contain
'Hello world'" for a site that was serving it — a false negative that read like
an application failure.
"""

from __future__ import annotations

from typing import Any, cast

from hop3_testing.apps.deployment import BODY_FETCH_LIMIT
from hop3_testing.runners.deployment import DeploymentTestRunner


class _FakeSession:
    """Returns a passing HTTP result carrying a chosen body."""

    def __init__(self, body: str) -> None:
        self._body = body

    def test_http_detailed(self, path: str, expected_status: Any) -> dict[str, Any]:
        return {
            "passed": True,
            "message": "ok",
            "details": {"body_preview": self._body, "status_code": 200},
        }


def _validate(body: str, contains: str) -> str | None:
    runner = DeploymentTestRunner(target=cast("Any", object()), cleanup=True)
    return runner._run_http_validation(
        cast("Any", _FakeSession(body)), "/", 200, contains, []
    )


def test_limit_fits_a_real_page() -> None:
    """16 KB was smaller than a modern CMS front page's inlined <head>."""
    assert BODY_FETCH_LIMIT >= 200_000


def test_miss_on_a_truncated_body_is_flagged_as_possibly_false() -> None:
    error = _validate("x" * BODY_FETCH_LIMIT, "Hello world")
    assert error is not None
    assert "false negative" in error
    assert str(BODY_FETCH_LIMIT) in error


def test_miss_on_a_short_body_carries_no_caveat() -> None:
    """A body well under the limit really does lack the marker."""
    error = _validate("<html>nothing here</html>", "Hello world")
    assert error is not None
    assert "false negative" not in error


def test_present_marker_passes() -> None:
    assert _validate("<html>Hello world</html>", "Hello world") is None
