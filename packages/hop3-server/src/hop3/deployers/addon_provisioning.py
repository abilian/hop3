# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Addon provisioning during deployment.

This module handles automatic provisioning of addons declared in hop3.toml.
When an app is deployed, addons specified in [[addons]] sections are:
1. Created if they don't exist
2. Attached to the app (connection details injected as env vars)

This enables declarative deployments where a single `hop3 deploy` handles
all backing service dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.credentials import get_credential_encryptor
from hop3.core.plugins import get_addon
from hop3.lib import log
from hop3.lib.logging import server_log
from hop3.orm import AddonCredential, EnvVar

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm.app import App


def provision_addons(
    app: App,
    addon_configs: list[dict],
    db_session: Session,
) -> None:
    """Provision addons declared in hop3.toml.

    For each addon in the config:
    1. Generate addon name (app_name-addon_type)
    2. Create addon if it doesn't exist
    3. Attach addon to app if not already attached

    Args:
        app: The application model
        addon_configs: List of addon dicts from hop3.toml [[addons]] sections
        db_session: Database session for persistence
    """
    if not addon_configs:
        return

    server_log.info(
        "Provisioning addons from config",
        app_name=app.name,
        addon_count=len(addon_configs),
    )

    for addon_config in addon_configs:
        addon_type = addon_config.get("type")
        if not addon_type:
            log("  Skipping addon with no type", level=1, fg="yellow")
            continue

        # Use explicit name if provided, otherwise generate from app name
        addon_name = addon_config.get("name", f"{app.name}-{addon_type}")

        _provision_single_addon(
            app=app,
            addon_type=addon_type,
            addon_name=addon_name,
            db_session=db_session,
        )


def _provision_single_addon(
    app: App,
    addon_type: str,
    addon_name: str,
    db_session: Session,
) -> None:
    """Provision a single addon.

    Creates the addon if it doesn't exist, then attaches it to the app.
    """
    log(f"  Provisioning addon: {addon_type} ({addon_name})", level=1, fg="blue")

    try:
        addon = get_addon(addon_type, addon_name)
    except RuntimeError as e:
        log(f"  Unknown addon type: {addon_type}", level=0, fg="red")
        server_log.error("Unknown addon type", addon_type=addon_type, error=str(e))
        return

    # Always call create() - it's idempotent and handles:
    # - Creating new addon if it doesn't exist
    # - Regenerating password if secrets are missing (e.g., after server reinstall)
    # - Doing nothing if addon already exists with secrets
    log(f"  Ensuring addon {addon_name} exists...", level=2)
    try:
        addon.create()
        server_log.info(
            "Ensured addon exists", addon_name=addon_name, addon_type=addon_type
        )
    except Exception as e:
        log(f"  Failed to create addon {addon_name}: {e}", level=0, fg="red")
        server_log.error(
            "Failed to create addon",
            addon_name=addon_name,
            addon_type=addon_type,
            error=str(e),
        )
        return

    # Check if already attached to this app
    existing_credential = (
        db_session
        .query(AddonCredential)
        .filter_by(app_id=app.id, addon_type=addon_type, addon_name=addon_name)
        .first()
    )

    # Get connection details and attach
    try:
        connection_details = addon.get_connection_details()
    except Exception as e:
        log(
            f"  Failed to get connection details for {addon_name}: {e}",
            level=0,
            fg="red",
        )
        server_log.error(
            "Failed to get connection details",
            addon_name=addon_name,
            error=str(e),
        )
        return

    if not connection_details:
        log(f"  No connection details from addon {addon_name}", level=0, fg="yellow")
        return

    # Store credential
    encryptor = get_credential_encryptor()
    if existing_credential:
        # Update existing credential
        existing_credential.encrypted_data = encryptor.encrypt(connection_details)
    else:
        # Create new credential
        credential = AddonCredential(
            app_id=app.id,
            addon_type=addon_type,
            addon_name=addon_name,
            encrypted_data=encryptor.encrypt(connection_details),
        )
        db_session.add(credential)

    # Add env vars to app (addons can update existing values, e.g., when password changes)
    _inject_env_vars(app, connection_details, db_session)

    log(f"  Attached addon {addon_name} to {app.name}", level=1, fg="green")
    server_log.info(
        "Attached addon",
        addon_name=addon_name,
        addon_type=addon_type,
        app_name=app.name,
        env_vars=list(connection_details.keys()),
    )


def inject_config_env_vars(
    app: App,
    env_config: dict[str, str],
    db_session: Session,
) -> None:
    """Inject environment variables from hop3.toml [env] section.

    These are treated as defaults: they will only be set if the variable
    doesn't exist or was previously set from hop3.toml. User-set values
    (via config:set) and addon values are preserved.

    Args:
        app: The application model
        env_config: Dict of env var name -> value from hop3.toml
        db_session: Database session for persistence
    """
    if not env_config:
        return

    server_log.info(
        "Injecting env vars from config",
        app_name=app.name,
        env_var_count=len(env_config),
    )

    injected_count = _inject_env_vars(app, env_config, db_session, defaults_only=True)

    log(
        f"  Injected {injected_count} env var(s) from hop3.toml",
        level=1,
        fg="green",
    )


def _inject_env_vars(
    app: App,
    env_vars: dict[str, str],
    db_session: Session,
    *,
    defaults_only: bool = False,
) -> int:
    """Inject environment variables into an app.

    Args:
        app: The application model
        env_vars: Dict of env var name -> value
        db_session: Database session for persistence
        defaults_only: If True, only create new vars, never overwrite existing ones

    Returns:
        Number of env vars actually injected/updated
    """
    injected = 0

    for key, value in env_vars.items():
        # Check if variable already exists
        existing = None
        for env_var in app.env_vars:
            if env_var.name == key:
                existing = env_var
                break

        if existing:
            if defaults_only:
                # hop3.toml provides defaults only - don't overwrite
                continue
            existing.value = str(value)
            injected += 1
        else:
            new_var = EnvVar(app_id=app.id, name=key, value=str(value))
            db_session.add(new_var)
            app.env_vars.append(new_var)
            injected += 1

    return injected
