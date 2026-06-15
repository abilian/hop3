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
from hop3.deployers.env_provisioning import set_env_vars
from hop3.lib import log
from hop3.lib.logging import server_log
from hop3.orm import AddonCredential
from hop3.orm.repositories import AddonCredentialRepository

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
        explicit_name = addon_config.get("name")
        # Legacy form (older [[addons]] and the deprecated [[provider]] alias):
        # `name` doubled as the type, with no separate instance name. The schema
        # documents `name` as "legacy: also used as type", so honor it here
        # rather than dropping the addon.
        if not addon_type and explicit_name:
            addon_type = explicit_name
            explicit_name = None

        if not addon_type:
            # Never silently skip a declared addon: the app would deploy without
            # its backing service and then fail confusingly downstream (e.g. a
            # migration with no database). Refuse loudly, where the user looks.
            from hop3.lib import Diagnosis, abort_with_diagnosis  # noqa: PLC0415

            abort_with_diagnosis(
                Diagnosis(
                    component="Addon provisioning",
                    action="read an [[addons]] entry in hop3.toml",
                    reason="the entry has neither 'type' nor 'name'",
                    hint=(
                        "Set 'type' to a backing service, e.g. "
                        'type = "postgresql" (also: mysql, redis).'
                    ),
                    troubleshooting=[
                        '[[addons]]\\ntype = "postgresql"',
                        "hop3 addon list  # available addon types",
                    ],
                )
            )

        # Use explicit name if provided, otherwise generate from app name
        addon_name = explicit_name or f"{app.name}-{addon_type}"

        _provision_single_addon(
            app=app,
            addon_type=addon_type,
            addon_name=addon_name,
            addon_config=addon_config,
            db_session=db_session,
        )


def reinject_attached_addons(app: App, db_session: Session) -> None:
    """Re-derive the app's addon env vars from its stored credentials.

    On every deploy, each addon *attached* to the app — whether declared in
    ``hop3.toml [[addons]]`` or attached manually via ``hop3 addon attach`` —
    has its decrypted connection details re-injected into the runtime env. This
    makes the runtime env a function of the ``AddonCredential`` rows (the source
    of truth) rather than a one-time env-var write at attach time, so
    ``DATABASE_URL``/``REDIS_URL``/… always survive redeploys and any env churn.
    Without it, a manually-attached addon (not in ``hop3.toml``) is never
    re-injected and its env var can silently go missing on redeploy.
    """
    repo = AddonCredentialRepository(session=db_session)
    credentials = repo.get_by_app_id(app.id)
    if not credentials:
        return

    encryptor = get_credential_encryptor()
    for credential in credentials:
        try:
            details = encryptor.decrypt(credential.encrypted_data)
        except Exception as e:
            log(
                f"  Could not decrypt credentials for addon "
                f"'{credential.addon_name}': {e}",
                level=1,
                fg="yellow",
            )
            continue
        if details:
            set_env_vars(app, details, db_session)
            log(
                f"  Re-injected env from attached addon '{credential.addon_name}'",
                level=2,
            )


def _provision_single_addon(
    app: App,
    addon_type: str,
    addon_name: str,
    addon_config: dict,
    db_session: Session,
) -> None:
    """Provision a single addon.

    Creates the addon if it doesn't exist, then attaches it to the app.
    Honours optional per-addon config (e.g. ``extensions`` for postgres).
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
        # Install any app-declared Postgres extensions AS SUPERUSER.
        # This covers non-trusted extensions (bloom, postgis, pgvector)
        # that a per-app user cannot install even with CREATE grants,
        # and is idempotent (CREATE EXTENSION IF NOT EXISTS) for
        # trusted extensions too.
        extensions = addon_config.get("extensions") or []
        if extensions and hasattr(addon, "install_extensions"):
            log(
                f"  Installing extensions on {addon_name}: {', '.join(extensions)}",
                level=2,
            )
            addon.install_extensions(extensions)
        server_log.info(
            "Ensured addon exists", addon_name=addon_name, addon_type=addon_type
        )
    except Exception as e:
        from hop3.lib import Diagnosis, abort_with_diagnosis  # noqa: PLC0415

        log(f"  Failed to create addon {addon_name}: {e}", level=0, fg="red")
        server_log.error(
            "Failed to create addon",
            addon_name=addon_name,
            addon_type=addon_type,
            error=str(e),
        )
        abort_with_diagnosis(
            Diagnosis(
                component="Addon provisioning",
                action=f"provision {addon_type} addon '{addon_name}'",
                reason=str(e),
                hint=(
                    f"Check that {addon_type} is installed and running on "
                    f"the server. You may need to re-run the installer "
                    f"with '--with {addon_type}'"
                ),
                troubleshooting=[
                    f"hop3-install server --with {addon_type}",
                    (f"systemctl status {addon_type} (or supervisorctl status)"),
                    "hop3 addon list",
                ],
            )
        )

    # Check if already attached to this app
    addon_credential_repo = AddonCredentialRepository(session=db_session)
    existing_credential = addon_credential_repo.get_by_app_addon(
        app_id=app.id, addon_type=addon_type, addon_name=addon_name
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
        addon_credential_repo.update(existing_credential)
    else:
        # Create new credential
        credential = AddonCredential(
            app_id=app.id,
            addon_type=addon_type,
            addon_name=addon_name,
            encrypted_data=encryptor.encrypt(connection_details),
        )
        addon_credential_repo.add(credential)

    # Add env vars to app (addons can update existing values, e.g., when password changes)
    set_env_vars(app, connection_details, db_session)  # Return value unused here

    log(f"  Attached addon {addon_name} to {app.name}", level=1, fg="green")
    server_log.info(
        "Attached addon",
        addon_name=addon_name,
        addon_type=addon_type,
        app_name=app.name,
        env_vars=list(connection_details.keys()),
    )
