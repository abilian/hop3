# Copyright (c) 2023-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Validators for user-facing identifiers that flow into shell commands, file
paths, or proxy configs.

Every user-controlled string that ends up in an `sh -c` payload, a
filesystem path under ``APP_ROOT``, or a reverse-proxy config file must
pass through one of these validators before leaving the RPC boundary.
"""

from __future__ import annotations

import re

__all__ = [
    "APP_NAME_RE",
    "ENV_VAR_KEY_RE",
    "HOSTNAME_RE",
    "InvalidIdentifierError",
    "validate_app_name",
    "validate_env_var_key",
    "validate_hostname",
    "validate_hostname_list",
    "validate_service_name",
]


# App-name rule: starts and ends with an alphanumeric character, may contain
# hyphens and underscores in between, total length 3-63. Matches the existing
# dashboard rule (letters, digits, '-', '_') but tightens it so the name is
# always safe as a filesystem path segment and as a Docker Compose service
# identifier. Examples accepted: ``myapp``, ``110-flask-gunicorn``,
# ``user_service_v2``. Rejected: ``..``, ``_leading``, ``-x``, ``app.evil``.
APP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]$")

# POSIX environment variable name: letter or underscore, then alphanumerics
# or underscores. We accept lower-case too because the existing codebase
# does (see `SENSITIVE_PATTERNS` upcasing in commands/_helpers.py); the
# crucial property is that no shell metacharacter can appear.
ENV_VAR_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# RFC 1123-style hostname: one or more dot-separated labels, each 1-63 chars,
# total length up to 253 chars. Labels must start and end with an alphanumeric
# and may contain hyphens in between.
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    r"(\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))*$"
)


class InvalidIdentifierError(ValueError):
    """Raised when a user-supplied identifier fails validation.

    A ``ValueError`` subclass so existing RPC error-handling paths that
    already catch ``ValueError`` turn these into the usual 400-class
    responses.
    """


def _validate_identifier(name: str, kind: str) -> str:
    """Validate ``name`` against ``APP_NAME_RE`` for the given ``kind``.

    ``kind`` is the lowercase noun (``"app"`` or ``"service"``) used to build
    the human-readable error messages. The capitalized form is used for the
    type-check message and the lowercase form for the format message, exactly
    matching the messages of the public wrappers.
    """
    if not isinstance(name, str):
        msg = f"{kind.capitalize()} name must be a string, got {type(name).__name__}"
        raise InvalidIdentifierError(msg)
    if not APP_NAME_RE.fullmatch(name):
        msg = (
            f"Invalid {kind} name {name!r}: must be 3-63 characters, start and "
            f"end with a letter or digit, and contain only letters, digits, "
            f"hyphens, and underscores."
        )
        raise InvalidIdentifierError(msg)
    return name


def validate_app_name(name: str) -> str:
    """Return ``name`` if it is a valid app identifier, else raise."""
    return _validate_identifier(name, "app")


def validate_service_name(name: str) -> str:
    """Return ``name`` if it is a valid Docker Compose service identifier."""
    return _validate_identifier(name, "service")


def validate_env_var_key(key: str) -> str:
    """Return ``key`` if it is a valid environment-variable identifier."""
    if not isinstance(key, str):
        msg = f"Env var key must be a string, got {type(key).__name__}"
        raise InvalidIdentifierError(msg)
    if not ENV_VAR_KEY_RE.fullmatch(key):
        msg = (
            f"Invalid env var key {key!r}: must start with a letter or "
            f"underscore and contain only letters, digits, and underscores "
            f"(max 64 chars)."
        )
        raise InvalidIdentifierError(msg)
    return key


def validate_hostname(host: str) -> str:
    """Return ``host`` if it is a valid RFC 1123 hostname, else raise.

    The catch-all token ``"_"`` is accepted because nginx uses it for the
    default server block, and the codebase treats it as a sentinel.
    """
    if not isinstance(host, str):
        msg = f"Hostname must be a string, got {type(host).__name__}"
        raise InvalidIdentifierError(msg)
    if host == "_":
        return host
    if not HOSTNAME_RE.fullmatch(host):
        msg = (
            f"Invalid hostname {host!r}: must be an RFC-1123 domain "
            f"(labels of letters/digits/hyphens separated by dots, max "
            f"253 chars total)."
        )
        raise InvalidIdentifierError(msg)
    return host


def validate_hostname_list(value: str) -> list[str]:
    """Parse and validate a comma- or whitespace-separated list of hostnames.

    Used where hop3.toml or env vars encode several aliases in one string
    (typically ``HOST_NAME = "example.com,www.example.com"``). Each entry
    is validated individually; empty entries are discarded.
    """
    if not isinstance(value, str):
        msg = f"Hostname list must be a string, got {type(value).__name__}"
        raise InvalidIdentifierError(msg)
    raw = value.replace(",", " ").split()
    hosts = [validate_hostname(item) for item in raw if item]
    if not hosts:
        msg = "Hostname list is empty"
        raise InvalidIdentifierError(msg)
    return hosts
