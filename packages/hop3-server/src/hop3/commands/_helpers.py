# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared helper functions for commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.orm import App, EnvVar
from hop3.orm.repositories import AppRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_app(db_session: Session, app_name: str) -> App:
    """Retrieve an app by name or raise a consistent error.

    Args:
        db_session: Database session
        app_name: Name of the application

    Returns:
        The App object

    Raises:
        ValueError: If the app is not found
    """
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
