# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Backup-related dashboard views."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse

from hop3.core.backup import BackupManager
from hop3.server.lib.database import get_session
from hop3.server.singletons import router, templates

from .utils import format_backup_datetime, format_size, require_auth

if TYPE_CHECKING:
    from starlette.requests import Request


@router.get("/dashboard/backups")
@require_auth
def dashboard_backups(request: Request):
    """Display backups page.

    Args:
        request: The HTTP request

    Returns:
        Template response with backups list
    """
    # Get all backups from database
    with get_session() as db_session:
        manager = BackupManager(db_session)
        backup_manifests = manager.list_backups(app_name=None, limit=100)

        # Convert to dict for template
        backups = []
        for manifest in backup_manifests:
            created = format_backup_datetime(manifest.backup_id, manifest.created_at)
            services_list = [s["name"] for s in manifest.services]

            backups.append({
                "backup_id": manifest.backup_id,
                "app_name": manifest.app_name,
                "created": created,
                "size": format_size(manifest.size_bytes),
                "services_count": len(manifest.services),
                "services": ", ".join(services_list) if services_list else "None",
            })

    ctx = {"backups": backups}
    return templates(request, "dashboard/backups.html", ctx)


@router.get("/dashboard/backups/{backup_id}/info")
@require_auth
def backup_info(request: Request):
    """Display detailed backup information.

    Args:
        request: The HTTP request

    Returns:
        Template response with backup details
    """
    backup_id = request.path_params["backup_id"]

    # Get backup info
    with get_session() as db_session:
        manager = BackupManager(db_session)

        try:
            manifest = manager.get_backup_info(backup_id)
            verification = manager.verify_backup(backup_id)
            all_valid = all(verification.values())

            # Prepare checksums with verification status
            checksums = []
            for filename, checksum in manifest.checksums.items():
                checksums.append({
                    "filename": filename,
                    "checksum": checksum,
                    "valid": verification.get(filename, False),
                })

            ctx = {
                "backup": {
                    "backup_id": manifest.backup_id,
                    "app_name": manifest.app_name,
                    "created_at": manifest.created_at,
                    "size": format_size(manifest.size_bytes),
                    "format_version": manifest.format_version,
                    "hop3_version": manifest.hop3_version,
                    "env_vars_count": manifest.env_vars_count,
                    "services": manifest.services,
                    "app_metadata": manifest.app_metadata,
                    "checksums": checksums,
                    "all_valid": all_valid,
                },
            }

            return templates(request, "dashboard/backup_info.html", ctx)

        except FileNotFoundError:
            return RedirectResponse(url="/dashboard/backups", status_code=302)
        except Exception as e:
            print(f"Error getting backup info: {e}")
            return RedirectResponse(url="/dashboard/backups", status_code=302)


@router.post("/dashboard/backups/{backup_id}/restore")
@require_auth
def backup_restore(request: Request):
    """Restore a backup.

    Args:
        request: The HTTP request

    Returns:
        Redirect to backups page
    """
    backup_id = request.path_params["backup_id"]

    with get_session() as db_session:
        manager = BackupManager(db_session)

        try:
            # Get backup info to know which app
            manifest = manager.get_backup_info(backup_id)

            # Perform restore
            manager.restore_backup(backup_id)

            print(f"Backup {backup_id} restored successfully to {manifest.app_name}")
        except Exception as e:
            print(f"Error restoring backup {backup_id}: {e}")

    return RedirectResponse(url="/dashboard/backups", status_code=303)


@router.post("/dashboard/backups/{backup_id}/delete")
@require_auth
def backup_delete(request: Request):
    """Delete a backup.

    Args:
        request: The HTTP request

    Returns:
        Redirect to backups page
    """
    backup_id = request.path_params["backup_id"]

    with get_session() as db_session:
        manager = BackupManager(db_session)

        try:
            manager.delete_backup(backup_id)
            print(f"Backup {backup_id} deleted successfully")
        except Exception as e:
            print(f"Error deleting backup {backup_id}: {e}")

    return RedirectResponse(url="/dashboard/backups", status_code=303)
