# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for env-var redaction (secret-leak prevention)."""

from __future__ import annotations

import pytest

from hop3.commands._helpers import redact_sensitive_value, set_env_var
from hop3.orm import App


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        # Name-based: password-like vars are masked to first 4 chars.
        ("MYSQL_PASSWORD", "Xht5Qj_c123", "Xht5***"),
        ("SECRET_KEY", "abcdefgh", "abcd***"),
        ("API_TOKEN", "x", "***"),
        # Value-based: credentials embedded in connection-string URLs are masked
        # even when the name doesn't look sensitive (the reported leak).
        (
            "DATABASE_URL",
            "mysql://u:Xht5Qj_c123@127.0.0.1:3306/db",
            "mysql://u:***@127.0.0.1:3306/db",
        ),
        # No-user form `scheme://:password@host`.
        ("REDIS_URL", "redis://:pw@host:6379/0", "redis://:***@host:6379/0"),
        # Non-sensitive values pass through untouched.
        ("DATA_DIR", "../data", "../data"),
        ("NODE_ENV", "production", "production"),
        # host:port without credentials must NOT be mistaken for user:pass.
        ("APP_URL", "https://host:8080/path", "https://host:8080/path"),
        # A DSN carries its key as colon-less userinfo, and the name matches no
        # password-like pattern — both layers used to miss it.
        ("SENTRY_DSN", "https://81e271568630473d8dd3ae@o44322.ingest.io/4", "http***"),
        (
            "REPORTING_URL",
            "https://81e271568630473d8dd3ae@o44322.ingest.io/4",
            "https://***@o44322.ingest.io/4",
        ),
        # A short colon-less userinfo is a username, not a token: keep it.
        (
            "GIT_REMOTE",
            "ssh://git@github.com/abilian/hop3",
            "ssh://git@github.com/abilian/hop3",
        ),
    ],
)
def test_redact_sensitive_value(name, value, expected):
    assert redact_sensitive_value(name, value) == expected


def test_redact_does_not_leak_password_substring():
    """The cleartext password must not survive anywhere in the output."""
    out = redact_sensitive_value("DATABASE_URL", "postgres://user:supersecret@h/db")
    assert "supersecret" not in out


def test_redact_does_not_leak_dsn_key():
    """A Sentry-style DSN key must not survive any display path."""
    dsn = "https://81e271568630473d8dd3ae@o44322.ingest.us.sentry.io/4511581"
    for name in ("SENTRY_DSN", "REPORTING_URL"):
        assert "81e271568630473d8dd3ae" not in redact_sensitive_value(name, dsn)


def test_set_env_var_does_not_echo_the_value():
    """`env set` prints its result back to the terminal: it must be redacted."""
    app = App(name="redact-demo")
    secret = "s3cret-value-not-in-output"

    created = set_env_var(app, "API_TOKEN", secret)
    updated = set_env_var(app, "API_TOKEN", "another-secret-value")

    assert secret not in created
    assert secret not in updated  # the *old* value leaks through "(was: ...)" too
    assert "API_TOKEN" in created
