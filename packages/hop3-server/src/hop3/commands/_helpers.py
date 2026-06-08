# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared helper functions for commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.identifiers import (
    InvalidIdentifierError,
    validate_app_name,
    validate_env_var_key,
)
from hop3.orm import App, EnvVar
from hop3.orm.repositories import AppRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Patterns that indicate sensitive environment variable values
SENSITIVE_PATTERNS: list[str] = [
    "PASSWORD",
    "SECRET",
    "KEY",
    "TOKEN",
    "CREDENTIAL",
    "API_KEY",
]


def redact_sensitive_value(name: str, value: str) -> str:
    """Redact sensitive values, showing only first 4 characters.

    Args:
        name: Environment variable name
        value: Environment variable value

    Returns:
        Redacted value if name matches sensitive patterns, original otherwise
    """
    if any(pattern in name.upper() for pattern in SENSITIVE_PATTERNS):
        if len(value) > 4:
            return value[:4] + "***"
        return "***"
    return value


def get_app(db_session: Session, app_name: str) -> App:
    """Retrieve an app by name or raise a consistent error.

    Args:
        db_session: Database session
        app_name: Name of the application

    Returns:
        The App object

    Raises:
        InvalidIdentifierError: If ``app_name`` fails identifier validation.
            This is the primary RPC-boundary choke point; rejecting here
            prevents path-traversal payloads from ever reaching
            ``App.app_path`` or touching the filesystem.
        ValueError: If the app is not found.
    """
    validate_app_name(app_name)
    app_repo = AppRepository(session=db_session)
    app = app_repo.get_one_or_none(name=app_name)
    if not app:
        msg = f"App '{app_name}' not found."
        raise ValueError(msg)
    return app


def parse_key_value_settings(
    settings: list[str],
) -> tuple[dict[str, str], list[str]]:
    """Parse KEY=VALUE settings from command line arguments.

    Args:
        settings: List of "KEY=VALUE" strings

    Returns:
        Tuple of (parsed_dict, errors) where:
        - parsed_dict maps keys to values
        - errors is a list of error messages for invalid settings
    """
    parsed: dict[str, str] = {}
    errors: list[str] = []

    for setting in settings:
        if "=" not in setting:
            errors.append(f"Invalid setting format: '{setting}' (expected KEY=VALUE)")
            continue

        key, value = setting.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            errors.append(f"Empty key in setting: '{setting}'")
            continue

        try:
            validate_env_var_key(key)
        except InvalidIdentifierError as e:
            errors.append(str(e))
            continue

        parsed[key] = value

    return parsed, errors


def set_env_var(app: App, key: str, value: str) -> str:
    """Set or update an environment variable on an app.

    Args:
        app: The application object
        key: Environment variable name
        value: Environment variable value

    Returns:
        Description of the change made
    """
    for env_var in app.env_vars:
        if env_var.name == key:
            old_value = env_var.value
            env_var.value = value
            return f"Updated {key}={value} (was: {old_value})"

    new_var = EnvVar(name=key, value=value, app=app)
    app.env_vars.append(new_var)
    return f"Set {key}={value}"


def unset_env_var(app: App, key: str) -> bool:
    """Remove an environment variable from an app.

    Args:
        app: The application object
        key: Environment variable name to remove

    Returns:
        True if the variable was found and removed, False otherwise
    """
    for env_var in app.env_vars:
        if env_var.name == key:
            app.env_vars.remove(env_var)
            return True
    return False


def parse_hostname_string(value: str | None) -> list[str]:
    """Split a HOST_NAME string into individual hostnames.

    Accepts comma- or whitespace-separated forms. Does NOT validate
    syntax — use ``validate_hostname_list`` for that. Use this when
    reading already-stored values, where the canonical form is
    space-separated but legacy data may use commas.
    """
    return [h for h in (value or "").replace(",", " ").split() if h]


def check_hostname_conflict(
    db_session: Session,
    current_app_name: str,
    new_hosts: list[str],
) -> tuple[str, str] | None:
    """Return (app, host) if any of new_hosts is already used by another app.

    Args:
        db_session: Database session.
        current_app_name: App being modified (excluded from the scan).
        new_hosts: Pre-parsed hostnames to check.

    Returns:
        Tuple of (conflicting_app_name, conflicting_host) on overlap,
        else None.
    """
    new_set = set(new_hosts)
    if not new_set:
        return None

    app_repo = AppRepository(session=db_session)
    for app in app_repo.get_many():
        if app.name == current_app_name:
            continue
        for env_var in app.env_vars:
            if env_var.name != "HOST_NAME" or not env_var.value:
                continue
            existing = set(parse_hostname_string(env_var.value))
            overlap = new_set & existing
            if overlap:
                return (app.name, min(overlap))
    return None
