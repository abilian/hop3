# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for env-var redaction (secret-leak prevention)."""

from __future__ import annotations

import pytest

from hop3.commands._helpers import redact_sensitive_value


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
    ],
)
def test_redact_sensitive_value(name, value, expected):
    assert redact_sensitive_value(name, value) == expected


def test_redact_does_not_leak_password_substring():
    """The cleartext password must not survive anywhere in the output."""
    out = redact_sensitive_value("DATABASE_URL", "postgres://user:supersecret@h/db")
    assert "supersecret" not in out
