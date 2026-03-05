# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Environment variable provisioning during deployment.

This module handles injection of environment variables from hop3.toml [env] section.
Values from hop3.toml are treated as defaults - they only create new variables
and never overwrite existing ones (set via config:set or addon provisioning).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.lib import log
from hop3.lib.logging import server_log
from hop3.orm import EnvVar

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm.app import App


def set_default_env_vars(
    app: App,
    env_config: dict[str, str],
    db_session: Session,
) -> None:
    """Set default environment variables from hop3.toml [env] section.

    These are defaults only: they create new variables but never overwrite
    existing ones. User-set values (via config:set) and addon values are preserved.

    Args:
        app: The application model
        env_config: Dict of env var name -> value from hop3.toml
        db_session: Database session for persistence
    """
    if not env_config:
        return

    server_log.info(
        "Setting default env vars from config",
        app_name=app.name,
        env_var_count=len(env_config),
    )

    injected_count = set_env_vars(app, env_config, db_session, defaults_only=True)

    log(
        f"  Set {injected_count} env var(s) from hop3.toml",
        level=1,
        fg="green",
    )


def set_env_vars(
    app: App,
    env_vars: dict[str, str],
    db_session: Session,
    *,
    defaults_only: bool = False,
) -> int:
    """Set environment variables on an app.

    Args:
        app: The application model
        env_vars: Dict of env var name -> value
        db_session: Database session for persistence
        defaults_only: If True, only create new vars, never overwrite existing ones

    Returns:
        Number of env vars actually set/updated
    """
    count = 0

    for key, value in env_vars.items():
        existing = None
        for env_var in app.env_vars:
            if env_var.name == key:
                existing = env_var
                break

        if existing:
            if defaults_only:
                continue
            existing.value = str(value)
            count += 1
        else:
            new_var = EnvVar(app_id=app.id, name=key, value=str(value))
            db_session.add(new_var)
            app.env_vars.append(new_var)
            count += 1

    return count
