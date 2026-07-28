# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The support library an app's ``check.py`` imports (``hop3.server.checks``).

What matters is that it never degrades a check into a weaker assertion: a smoke
test that quietly tests less than it claims is worse than no test at all.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from hop3.server import checks as hop3check


def test_missing_credentials_fail_loudly(monkeypatch):
    """
    No credential must FAIL, never skip.

    A check that silently proceeds without credentials would report "passed"
    for an app whose sign-in was never exercised.
    """
    monkeypatch.delenv("HOP3_ADMIN_PASSWORD", raising=False)
    check = hop3check.Check("app.example.com", 443)

    with pytest.raises(hop3check.CheckError, match="no admin credential"):
        _ = check.admin


def test_credentials_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("HOP3_ADMIN_USER", "admin")
    monkeypatch.setenv("HOP3_ADMIN_EMAIL", "ops@example.com")
    monkeypatch.setenv("HOP3_ADMIN_PASSWORD", "s3cret")

    admin = hop3check.Check("app.example.com", 443).admin

    assert admin.username == "admin"
    assert admin.email == "ops@example.com"
    assert admin.password == "s3cret"
    assert admin.identity == "admin"


def test_identity_falls_back_to_email():
    """Apps keyed by email declare no username; identity must still resolve."""
    admin = hop3check.Admin(username="", email="ops@example.com", password="x")
    assert admin.identity == "ops@example.com"


def test_a_missing_token_fails_rather_than_posting_without_it():
    """
    An absent CSRF token must FAIL the check.

    Posting with an empty token turns a credential test into a token-rejection
    test — indistinguishable from outside, and it would mask a real sign-in bug.
    """
    check = hop3check.Check("app.example.com", 443)

    with pytest.raises(hop3check.CheckError, match="could not find the requesttoken"):
        check.extract(
            "<html>no token here</html>",
            r'name="tok" value="([^"]+)"',
            what="requesttoken",
        )


def test_extract_returns_the_capture_group():
    check = hop3check.Check("app.example.com", 443)
    html = '<input name="_token" value="abc123">'
    assert check.extract(html, r'name="_token" value="([^"]+)"') == "abc123"


def test_checks_run_over_https():
    """
    A sign-in check must use HTTPS even though the harness passes port 80.

    Apps served over HTTPS issue Secure session cookies, which are never sent
    back over plain HTTP — so a sign-in tested over HTTP fails however correct
    the credential is, and every app would look broken.
    """
    check = hop3check.Check("app.example.com", 80)
    assert check.base_url.startswith("https://")


def test_expect_status_names_what_it_wanted():
    check = hop3check.Check("app.example.com", 443)

    response = SimpleNamespace(
        status_code=404,
        request=SimpleNamespace(method="GET", url=SimpleNamespace(path="/login")),
    )

    with pytest.raises(hop3check.CheckError, match="returned 404, expected 200"):
        check.expect_status(response, 200)
