# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Screenshots and the sign-ins only a browser can verify.

Ten catalog recipes build their sign-in form in JavaScript, so their check
verifies everything else and prints ``SIGN-IN VERIFIED BY BROWSER``. The
harness ignored the marker and reported them passed, so their sign-in was
never verified by a `hop3-test` run.
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from click.testing import CliRunner
from hop3_testing.cli import cli
from hop3_testing.exceptions import BrowserSignInError
from hop3_testing.results.reporters import ConsoleReporter
from hop3_testing.results.store import _derive_status
from hop3_testing.runners.base import TestResult, ValidationResult
from hop3_testing.runners.deployment import (
    BROWSER_REQUIRED_MARKER,
    browser_sign_in,
    sign_in_verdict,
)
from hop3_testing.screenshots import (
    ScreenshotError,
    ScreenshotOutcome,
    SignIn,
    _identifier_for,
    override_for,
    recipe_screenshot_dir,
)

from hop3.server.checks._helper import BROWSER_REQUIRED_MARKER as PRINTED_MARKER

_CHECK_OUTPUT = (
    "check: dolibarr.test.local (via https://dolibarr.test.local)\n"
    "\nSIGN-IN VERIFIED BY BROWSER: the login form is built by JavaScript\n"
)
_SIGNED_IN = ScreenshotOutcome(
    written=(Path("d-01-login.png"), Path("d-02-signed-in.png"))
)


def _check(output: str) -> list[ValidationResult]:
    return [
        ValidationResult(
            passed=True,
            message="check.py passed on server",
            duration=1.0,
            validation_type="check_script",
            details={"output": output},
        )
    ]


class TestTheBrowserMarker:
    def test_the_marker_is_read_with_its_reason(self):
        assert (
            browser_sign_in(_check(_CHECK_OUTPUT))
            == "the login form is built by JavaScript"
        )

    def test_a_check_that_signed_in_leaves_nothing_to_the_browser(self):
        assert browser_sign_in(_check("check: x\nOK\n")) is None


class TestTheVerdict:
    def test_without_a_browser_the_pass_says_what_it_left(self):
        unverified = sign_in_verdict("JS form", None)

        assert "needs a browser (JS form)" in unverified
        assert "--screenshots" in unverified

    def test_a_signed_in_shot_verifies_it(self):
        assert sign_in_verdict("JS form", _SIGNED_IN) == ""

    def test_a_browser_that_could_not_sign_in_fails_the_test(self):
        refused = ScreenshotOutcome(
            written=(Path("d-01-login.png"),), problem="still on a sign-in form"
        )

        with pytest.raises(BrowserSignInError, match="still on a sign-in form"):
            sign_in_verdict("JS form", refused)

    def test_an_app_whose_check_signed_in_needs_no_browser(self):
        assert sign_in_verdict(None, None) == ""


def _result(*, passed: bool = True, unverified: str = "", shots=None) -> TestResult:
    test = SimpleNamespace(
        name="dolibarr", expects_failure=False, app_path=Path("dolibarr")
    )
    return TestResult(
        test=cast("Any", test),
        passed=passed,
        unverified=unverified,
        screenshots=shots,
    )


def test_an_unverified_pass_is_stored_as_such():
    assert _derive_status(_result(unverified="its sign-in needs a browser")) == (
        "unverified"
    )
    assert _derive_status(_result()) == "pass"


def test_the_summary_names_what_was_not_verified():
    out = io.StringIO()
    reporter = ConsoleReporter(output=out, quiet=True)

    reporter.summary([_result(unverified="its sign-in needs a browser (JS form)")])

    text = out.getvalue()
    assert "not fully verified" in text
    assert "dolibarr: its sign-in needs a browser (JS form)" in text
    assert "All 1 tests passed!" not in text


def test_the_screenshot_count_counts_every_app_asked_for():
    """It once printed 8/8 over twelve apps that failed before their shots."""
    out = io.StringIO()
    reporter = ConsoleReporter(output=out, quiet=True)
    failed = ScreenshotOutcome(problem="not taken: the test failed first")

    reporter.summary([_result(shots=_SIGNED_IN), _result(passed=False, shots=failed)])

    text = out.getvalue()
    assert "Screenshots: 1/2 app(s) photographed signed in" in text
    assert "not taken: the test failed first" in text


class TestSignIn:
    def test_an_app_that_signs_in_by_email_is_offered_the_email(self):
        sign_in = SignIn.from_credentials(
            "directus",
            "https://directus.test.local",
            "203.0.113.5",
            {
                "HOP3_ADMIN_USER": "admin",
                "HOP3_ADMIN_EMAIL": "op@example.com",
                "HOP3_ADMIN_PASSWORD": "pw",
                "HOP3_ADMIN_LOGIN": "email",
            },
        )

        assert sign_in.identifier == "op@example.com"

    def test_otherwise_the_username(self):
        sign_in = SignIn.from_credentials(
            "gitea",
            "https://gitea.test.local",
            "203.0.113.5",
            {"HOP3_ADMIN_USER": "admin", "HOP3_ADMIN_PASSWORD": "pw"},
        )

        assert sign_in.identifier == "admin"

    def test_no_credential_is_said_so(self):
        with pytest.raises(ScreenshotError, match="no admin credential"):
            SignIn.from_credentials("x", "https://x", "203.0.113.5", {})

    def test_an_email_field_gets_the_email_even_when_the_app_takes_a_name(self):
        """paheko signs in by name and renders <input type=email>."""
        sign_in = SignIn("paheko", "https://p", "h", "admin", "pw", "op@example.com")

        assert _identifier_for("email", sign_in) == "op@example.com"
        assert _identifier_for("text", sign_in) == "admin"


def test_a_variant_gets_its_native_apps_override():
    assert override_for("limesurvey-nix").login_path.endswith("/login")
    assert override_for("limesurvey-nixgen") == override_for("limesurvey")


def test_images_go_beside_the_recipe(tmp_path):
    (tmp_path / "golden" / "gitea").mkdir(parents=True)

    assert recipe_screenshot_dir(tmp_path, "gitea") == (
        tmp_path / "golden" / "gitea" / "screenshots"
    )
    assert recipe_screenshot_dir(tmp_path, "010-flask") is None


def test_screenshots_are_refused_on_docker_before_anything_starts():
    result = CliRunner().invoke(cli, ["run", "--docker", "--screenshots"])

    assert result.exit_code == 1
    assert "--screenshots needs a server" in result.output


def test_the_marker_is_the_one_the_server_prints():
    """Two spellings of one contract drift: the harness reads what checks write."""
    assert BROWSER_REQUIRED_MARKER == PRINTED_MARKER


def test_a_prefixed_marker_line_keeps_its_whole_reason():
    output = "->   check: SIGN-IN VERIFIED BY BROWSER: form built by JS: v6\n"

    assert browser_sign_in(_check(output)) == "form built by JS: v6"
