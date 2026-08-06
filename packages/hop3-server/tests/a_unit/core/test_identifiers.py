# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for hop3.core.identifiers."""

from __future__ import annotations

import pytest

from hop3.core.identifiers import (
    InvalidIdentifierError,
    validate_app_name,
    validate_env_var_key,
    validate_hostname,
    validate_hostname_list,
    validate_service_name,
)

# ---------------------------------------------------------------------------
# App name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "myapp",
        "my-app",
        "My-App",
        "110-flask-gunicorn-poetry",
        "user_service_v2",
        "APP1",
        "a12",
    ],
)
def test_validate_app_name_accepts(name: str) -> None:
    assert validate_app_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "ab",  # too short
        "-leading",
        "trailing-",
        "_leading",
        "trailing_",
        "..",
        "../evil",
        "my/app",
        "my\\app",
        "my.app",
        "my app",
        "my;app",
        "my\napp",
        "my\x00app",
        "a" * 64,  # too long
    ],
)
def test_validate_app_name_rejects(name: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_app_name(name)


def test_validate_app_name_rejects_non_string() -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_app_name(None)
    with pytest.raises(InvalidIdentifierError):
        validate_app_name(123)


# ---------------------------------------------------------------------------
# Service name (alias of app-name rule)
# ---------------------------------------------------------------------------


def test_validate_service_name_shares_app_name_rule() -> None:
    assert validate_service_name("web") is None or True
    # Accept ordinary Compose-style names.
    for name in ["web", "db1", "worker-1", "api_v2"]:
        assert validate_service_name(name) == name


@pytest.mark.parametrize("name", ["--rm", "svc;rm -rf /", "svc:foo", "svc$(id)"])
def test_validate_service_name_rejects(name: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_service_name(name)


# ---------------------------------------------------------------------------
# Env var key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "FOO",
        "HOST_NAME",
        "DATABASE_URL",
        "_PRIVATE",
        "_",
        "mixedCase",
        "a",
        "X" * 64,
    ],
)
def test_validate_env_var_key_accepts(key: str) -> None:
    assert validate_env_var_key(key) == key


@pytest.mark.parametrize(
    "key",
    [
        "",
        "1DIGIT",  # starts with digit
        "FOO BAR",  # space
        "FOO=bar",  # '=' appeared before the split
        "FOO;touch /tmp/x",
        "FOO$VAR",
        "FOO`cmd`",
        "FOO\nBAR",
        "FOO\x00BAR",
        "a" * 65,  # too long
    ],
)
def test_validate_env_var_key_rejects(key: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_env_var_key(key)


# ---------------------------------------------------------------------------
# Hostname
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "sub.example.com",
        "a",
        "my-app.example.co.uk",
        "_",  # nginx catch-all
        "xn--fiqs8s.cn",  # punycode
    ],
)
def test_validate_hostname_accepts(host: str) -> None:
    assert validate_hostname(host) == host


@pytest.mark.parametrize(
    "host",
    [
        "",
        "example.com;",  # directive injection
        "example.com\n",  # newline injection
        "example.com\nalias /;",
        "example.com/path",
        "example..com",
        "-leading.example.com",
        "trailing-.example.com",
        "a" * 254 + ".com",
    ],
)
def test_validate_hostname_rejects(host: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_hostname(host)


def test_validate_hostname_list_comma_separated() -> None:
    result = validate_hostname_list("example.com,www.example.com")
    assert result == ["example.com", "www.example.com"]


def test_validate_hostname_list_space_separated() -> None:
    result = validate_hostname_list("example.com www.example.com")
    assert result == ["example.com", "www.example.com"]


def test_validate_hostname_list_rejects_any_invalid_host() -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_hostname_list("example.com,evil\nalias /;")


def test_validate_hostname_list_rejects_empty_string() -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_hostname_list(",")
