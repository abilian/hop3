# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Addon provisioning during deployment.

This module handles automatic provisioning of addons declared in hop3.toml.
When an app is deployed, addons specified in [[addons]] sections are:
1. Created if they don't exist
2. Attached to the app (connection details injected as env vars)

This enables declarative deployments where a single `hop3 deploy` handles
all backing service dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from hop3.core.credentials import get_credential_encryptor
from hop3.core.plugins import get_addon
from hop3.deployers.env_provisioning import set_env_vars
from hop3.lib import log
from hop3.lib.logging import server_log
from hop3.orm import AddonCredential
from hop3.orm.repositories import AddonCredentialRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, scoped_session

    from hop3.orm.app import App

    # The session a repository carries (advanced_alchemy types it as a union).
    DbSession = Session | scoped_session[Session]


def _is_db_auth_failure(error: str) -> bool:
    """
    Whether a provisioning error is the DB rejecting our credential.

    A password/auth rejection means the service IS installed and reachable — the
    opposite of the "not installed" hint we'd otherwise show. (Postgres:
    "password authentication failed"; a missing password: "no password
    supplied"; MySQL: "access denied".)
    """
    e = error.lower()
    return (
        "authentication failed" in e
        or "no password supplied" in e
        or "access denied" in e
    )


def _addon_failure_guidance(addon_type: str, error: str) -> tuple[str, list[str]]:
    """
    Pick an actionable (hint, troubleshooting) for a provisioning failure.

    Distinguishes a credential mismatch (service up, wrong password) from a
    genuinely-missing service, so the operator isn't sent to re-run
    ``--with <type>`` for a problem that has nothing to do with installation.
    """
    if _is_db_auth_failure(error):
        toml = "/home/hop3/hop3-server.toml"
        if addon_type == "postgres":
            secret, cli = "POSTGRES_SUPERUSER_PASSWORD", "postgres"
        else:
            secret, cli = "MYSQL_SUPERUSER_PASSWORD", addon_type
        hint = (
            f"{addon_type} is reachable but rejected the superuser credential: "
            f"{secret} in {toml} does not match the live server's password. "
            "These drift when the DB cluster survives a redeploy that rewrote "
            "the config. Re-run the installer — it now re-asserts and verifies "
            "the superuser password against the running server."
        )
        return hint, [
            f"grep {secret} {toml}",
            f"hop3-install server --with {cli}",
            "hop3 addon list",
        ]

    if "left over from a previous app" in error:
        # The service is fine; the name collides with a database that outlived
        # its app. Sending the operator to reinstall the DB server would be
        # actively misleading — the remedy is already in the refusal itself.
        hint = (
            "The database server is healthy. A database of this name survived a "
            "previous app (a server rebuild reclaims Hop3's state but not the "
            "database server's), and attaching to it would hand this app the "
            "old one's data."
        )
        return hint, [
            "hop3 addon list",
            "drop the leftover database, or install the app under another name",
        ]

    hint = (
        f"Check that {addon_type} is installed and running on the server. "
        f"You may need to re-run the installer with '--with {addon_type}'"
    )
    return hint, [
        f"hop3-install server --with {addon_type}",
        f"systemctl status {addon_type} (or supervisorctl status)",
        "hop3 addon list",
    ]


def provision_addons(
    app: App,
    addon_configs: list[dict],
    db_session: Session,
) -> None:
    """
    Provision addons declared in hop3.toml.

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
            from hop3.lib import (  # ruff:ignore[import-outside-top-level]
                Diagnosis,
                abort_with_diagnosis,
            )

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


def addon_var_prefix(addon_name: str) -> str:
    """ENV-var prefix for a non-primary addon: NAME upper, '-'→'_', trailing '_'."""
    return addon_name.upper().replace("-", "_") + "_"


def compute_namespaced_vars(
    details: dict[str, str], *, is_primary: bool, addon_name: str
) -> dict[str, str]:
    """
    Namespace an addon's connection vars.

    Primary addon → ``details`` unchanged (unprefixed ``DATABASE_URL`` etc.);
    non-primary → every key prefixed with ``<ADDONNAME>_`` so several same-type
    addons can coexist on one app without clobbering each other.
    """
    if is_primary:
        return dict(details)
    prefix = addon_var_prefix(addon_name)
    return {f"{prefix}{key}": value for key, value in details.items()}


def _effective_primary_ids(credentials: list[AddonCredential]) -> set[int]:
    """
    Pick the effective primary credential id for each addon type.

    An explicit ``is_primary`` flag wins; if a type-group has none flagged
    (legacy data attached before this field, or a manually-created credential),
    the oldest (min id) is treated as primary — so a sole addon always injects
    the unprefixed vars and the unflagged case degrades sensibly.
    """
    by_type: dict[str, list[AddonCredential]] = {}
    for cred in credentials:
        by_type.setdefault(cred.addon_type, []).append(cred)
    primary_ids: set[int] = set()
    for group in by_type.values():
        ordered = sorted(group, key=lambda c: c.id)
        flagged = [c for c in ordered if c.is_primary]
        primary = flagged[0] if flagged else ordered[0]
        primary_ids.add(primary.id)
    return primary_ids


def sync_addon_env_vars(app: App, db_session: DbSession) -> dict[str, list[str]]:
    """
    Make the app's addon-injected env exactly match its AddonCredential rows.

    The single source of truth for addon env: attach, detach, promote and deploy
    all call this, so the runtime env is always a function of the credential rows
    (and their ``is_primary`` flags) — ``DATABASE_URL``/``REDIS_URL``/… survive
    redeploys, and a manually-attached addon is never lost.

    The set of names addons MANAGE is derived from the credentials, not a stored
    marker: for every attached credential, both the unprefixed and the prefixed
    spelling of each connection key. Any managed name not in the desired set is
    pruned — that is what drops the stale spelling when an addon flips between
    primary and non-primary (or is detached). The desired set is then upserted.

    Returns ``{"set": [names...], "removed": [names...]}``.
    """
    repo = AddonCredentialRepository(session=db_session)
    credentials = repo.get_by_app_id(app.id)
    encryptor = get_credential_encryptor()

    primary_ids = _effective_primary_ids(credentials)

    desired: dict[str, str] = {}
    managed_names: set[str] = set()
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
        if not details:
            continue
        prefix = addon_var_prefix(credential.addon_name)
        managed_names.update(details.keys())
        managed_names.update(f"{prefix}{key}" for key in details)
        desired.update(
            compute_namespaced_vars(
                details,
                is_primary=credential.id in primary_ids,
                addon_name=credential.addon_name,
            )
        )

    removed: list[str] = []
    for env_var in list(app.env_vars):
        if env_var.name in managed_names and env_var.name not in desired:
            app.env_vars.remove(env_var)  # delete-orphan cascade removes the row
            removed.append(env_var.name)

    if desired:
        set_env_vars(app, desired, cast("Session", db_session))
    db_session.flush()
    if desired or removed:
        log(
            f"  Synced addon env for '{app.name}': "
            f"{len(desired)} set, {len(removed)} removed",
            level=2,
        )
    return {"set": sorted(desired), "removed": sorted(removed)}


# Back-compat alias: the deploy path and tests import reinject_attached_addons.
reinject_attached_addons = sync_addon_env_vars


def addon_var_names(app: App, db_session: DbSession) -> set[str]:
    """
    Env-var names injected by the app's addons (both prefixed + unprefixed).

    Used to label a variable's source (addon vs user-set) in
    ``env show --sources``. Mirrors the managed-name set in
    ``sync_addon_env_vars`` so a non-primary addon's prefixed vars are counted.
    """
    repo = AddonCredentialRepository(session=db_session)
    encryptor = get_credential_encryptor()
    names: set[str] = set()
    for credential in repo.get_by_app_id(app.id):
        try:
            details = encryptor.decrypt(credential.encrypted_data)
        except Exception:
            continue
        prefix = addon_var_prefix(credential.addon_name)
        names.update(details.keys())
        names.update(f"{prefix}{key}" for key in details)
    return names


def _provision_single_addon(
    app: App,
    addon_type: str,
    addon_name: str,
    addon_config: dict,
    db_session: Session,
) -> None:
    """
    Provision a single addon.

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
        from hop3.lib import (  # ruff:ignore[import-outside-top-level]
            Diagnosis,
            abort_with_diagnosis,
        )

        log(f"  Failed to create addon {addon_name}: {e}", level=0, fg="red")
        server_log.error(
            "Failed to create addon",
            addon_name=addon_name,
            addon_type=addon_type,
            error=str(e),
        )
        hint, troubleshooting = _addon_failure_guidance(addon_type, str(e))
        abort_with_diagnosis(
            Diagnosis(
                component="Addon provisioning",
                action=f"provision {addon_type} addon '{addon_name}'",
                reason=str(e),
                hint=hint,
                troubleshooting=troubleshooting,
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
        # Update existing credential (keep its primary status).
        existing_credential.encrypted_data = encryptor.encrypt(connection_details)
        addon_credential_repo.update(existing_credential)
        is_primary = existing_credential.is_primary
    else:
        # Create new credential. The first addon of a type on this app is the
        # primary (unprefixed vars); a later same-type addon is non-primary.
        is_primary = not addon_credential_repo.list_by_app_and_type(app.id, addon_type)
        credential = AddonCredential(
            app_id=app.id,
            addon_type=addon_type,
            addon_name=addon_name,
            encrypted_data=encryptor.encrypt(connection_details),
            is_primary=is_primary,
        )
        addon_credential_repo.add(credential)

    # Inject this addon's env vars, namespaced by primary status. The deploy-level
    # sync_addon_env_vars (every deploy) reconciles the full picture afterwards.
    namespaced = compute_namespaced_vars(
        connection_details, is_primary=is_primary, addon_name=addon_name
    )
    set_env_vars(app, namespaced, db_session)

    log(f"  Attached addon {addon_name} to {app.name}", level=1, fg="green")
    server_log.info(
        "Attached addon",
        addon_name=addon_name,
        addon_type=addon_type,
        app_name=app.name,
        env_vars=list(connection_details.keys()),
    )
