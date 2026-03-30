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
    *,
    env_policy: str = "keep-existing",
) -> None:
    """Set environment variables from hop3.toml [env] section.

    By default, these are treated as defaults: they create new variables but
    never overwrite existing ones. When env_policy is "override", existing
    values are updated to match hop3.toml on every deploy.

    Args:
        app: The application model
        env_config: Dict of env var name -> value from hop3.toml
        db_session: Database session for persistence
        env_policy: "keep-existing" (default) or "override"
    """
    if not env_config:
        return

    defaults_only = env_policy != "override"

    server_log.info(
        "Setting env vars from config",
        app_name=app.name,
        env_var_count=len(env_config),
        policy=env_policy,
    )

    injected_count, skipped_names = set_env_vars(
        app, env_config, db_session, defaults_only=defaults_only
    )

    if injected_count:
        action = "Set" if defaults_only else "Set/updated"
        log(
            f"  {action} {injected_count} env var(s) from hop3.toml",
            level=1,
            fg="green",
        )
    if skipped_names:
        log(
            f"  Skipped {len(skipped_names)} env var(s) already set: "
            f"{', '.join(sorted(skipped_names))} "
            f"(use 'hop3 config:set' to update, or set _policy = \"override\" in [env])",
            level=1,
            fg="yellow",
        )


def set_env_vars(
    app: App,
    env_vars: dict[str, str],
    db_session: Session,
    *,
    defaults_only: bool = False,
) -> tuple[int, list[str]]:
    """Set environment variables on an app.

    Args:
        app: The application model
        env_vars: Dict of env var name -> value
        db_session: Database session for persistence
        defaults_only: If True, only create new vars, never overwrite existing ones

    Returns:
        Tuple of (count of env vars set/updated, list of skipped var names)
    """
    count = 0
    skipped: list[str] = []

    for key, value in env_vars.items():
        existing = None
        for env_var in app.env_vars:
            if env_var.name == key:
                existing = env_var
                break

        if existing:
            if defaults_only:
                skipped.append(key)
                continue
            existing.value = str(value)
            count += 1
        else:
            new_var = EnvVar(app_id=app.id, name=key, value=str(value))
            db_session.add(new_var)
            app.env_vars.append(new_var)
            count += 1

    return count, skipped


def set_computed_env_vars(
    app: App,
    computed_config: dict[str, str],
    db_session: Session,
) -> None:
    """Resolve and set computed environment variables from [env.computed].

    Computed vars use ${VAR} interpolation against the app's current env vars
    (including addon-injected ones). They always overwrite existing values.

    Args:
        app: The application model
        computed_config: Dict of var name -> template string (e.g., "${PGHOST}")
        db_session: Database session for persistence
    """
    if not computed_config:
        return

    from hop3.lib.templating import expand_vars  # noqa: PLC0415

    # Build current env snapshot for interpolation
    current_env = {ev.name: ev.value for ev in app.env_vars}

    resolved: dict[str, str] = {}
    for key, template in computed_config.items():
        value = expand_vars(str(template), current_env)
        # Check for unresolved variables (still contain ${...})
        if "${" in value:
            log(
                f"  WARNING: Unresolved variable in {key} = {template!r} "
                f"(resolved to {value!r}). Check that referenced vars are set.",
                level=0,
                fg="yellow",
            )
        resolved[key] = value

    # Set computed vars (always override — they're derived values)
    count, _ = set_env_vars(app, resolved, db_session, defaults_only=False)

    if count:
        log(
            f"  Set {count} computed env var(s) from [env.computed]",
            level=1,
            fg="green",
        )
