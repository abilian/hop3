# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard backups controller."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote_plus

from litestar import Controller, get, post
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3.core.backup import BackupManager
from hop3.lib.logging import server_log
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
)
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session

from .helpers import format_size

if TYPE_CHECKING:
    from collections.abc import Callable

    from litestar.params import FromPath
    from sqlalchemy.orm import Session


def _get_backup_manager(db_session: Session) -> BackupManager:
    """Create a BackupManager with repositories from the session."""
    return BackupManager(
        backup_repo=BackupRepository(session=db_session),
        app_repo=AppRepository(session=db_session),
        addon_credential_repo=AddonCredentialRepository(session=db_session),
    )


def _format_backup_datetime(backup_id: str, created_at: str) -> str:
    """Extract and format datetime from backup ID."""
    backup_id_parts = backup_id.split("_")
    if len(backup_id_parts) >= 2:
        date_str = backup_id_parts[0]
        time_str = backup_id_parts[1]
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
    return created_at


class BackupsController(Controller):
    """Controller for backup management routes."""

    path = "/dashboard/backups"
    guards = [auth_guard]  # ruff:ignore[mutable-class-default]

    @get("/", sync_to_thread=False)
    def dashboard_backups(self) -> Template | Redirect:
        """Display backups page."""
        with get_session() as db_session:
            manager = _get_backup_manager(db_session)
            backup_manifests = manager.list_backups(app_name=None, limit=100)

            backups = []
            for manifest in backup_manifests:
                created = _format_backup_datetime(
                    manifest.backup_id, manifest.created_at
                )
                addons_list = [s["name"] for s in manifest.addons]

                backups.append({
                    "backup_id": manifest.backup_id,
                    "app_name": manifest.app_name,
                    "created": created,
                    "size": format_size(manifest.size_bytes),
                    "addons_count": len(manifest.addons),
                    "addons": ", ".join(addons_list) if addons_list else "None",
                })

        ctx = {"backups": backups}
        return Template(template_name="dashboard/backups.html", context=ctx)

    @get("/{backup_id:str}/info", sync_to_thread=False)
    def backup_info(self, backup_id: FromPath[str]) -> Template | Redirect:
        """Display detailed backup information."""
        with get_session() as db_session:
            manager = _get_backup_manager(db_session)

            try:
                manifest = manager.get_backup_info(backup_id)
                verification = manager.verify_backup(backup_id)
                all_valid = all(verification.values())

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
                        "addons": manifest.addons,
                        "app_metadata": manifest.app_metadata,
                        "checksums": checksums,
                        "all_valid": all_valid,
                    },
                }

                return Template(template_name="dashboard/backup_info.html", context=ctx)

            except FileNotFoundError:
                return Redirect(path="/dashboard/backups")
            except Exception as e:
                server_log.exception(
                    "Could not read backup info", backup_id=backup_id, error=str(e)
                )
                reason = quote_plus(f"{type(e).__name__}: {e}")
                return Redirect(
                    path=f"/dashboard/backups?success=false&error={reason}",
                    status_code=HTTP_303_SEE_OTHER,
                )

    # Restore untars an archive and reloads addon databases; delete removes an
    # archive. Both are multi-second filesystem/DB work and the server runs one
    # worker, so they are offloaded to a thread — on the loop they would freeze
    # every other request (see the note in dashboard/apps.py).

    @post("/{backup_id:str}/restore", status_code=303, sync_to_thread=True)
    def backup_restore(self, backup_id: FromPath[str]) -> Redirect:
        """Restore a backup."""

        def _restore(manager: BackupManager) -> str:
            manifest = manager.get_backup_info(backup_id)
            manager.restore_backup(backup_id)
            return f"Restored backup {backup_id} to {manifest.app_name}"

        return self._run_backup_action(backup_id, "restore", _restore)

    @post("/{backup_id:str}/delete", status_code=303, sync_to_thread=True)
    def backup_delete(self, backup_id: FromPath[str]) -> Redirect:
        """Delete a backup."""

        def _delete(manager: BackupManager) -> str:
            manager.delete_backup(backup_id)
            return f"Deleted backup {backup_id}"

        return self._run_backup_action(backup_id, "delete", _delete)

    def _run_backup_action(
        self, backup_id: str, action: str, do: Callable[[BackupManager], str]
    ) -> Redirect:
        """
        Run one backup mutation and report its real outcome to the browser.

        A failed **restore** used to be pixel-identical to a successful one:
        the exception went to the server's stdout via `print()` and the browser
        got the same redirect either way. For an operation whose whole purpose
        is recovering data, silently reporting success is the worst available
        failure mode, and the project's fail-loud rule forbids it outright.
        """
        with get_session() as db_session:
            manager = _get_backup_manager(db_session)
            try:
                message = do(manager)
            except Exception as e:
                db_session.rollback()
                server_log.exception(
                    "Dashboard backup action failed",
                    backup_id=backup_id,
                    action=action,
                    error=str(e),
                )
                reason = quote_plus(f"{type(e).__name__}: {e}")
                return Redirect(
                    path=f"/dashboard/backups?action={action}&success=false&error={reason}",
                    status_code=HTTP_303_SEE_OTHER,
                )
            server_log.info(
                "Backup action succeeded", backup_id=backup_id, action=action
            )

        return Redirect(
            path=f"/dashboard/backups?action={action}&success=true&message={quote_plus(message)}",
            status_code=HTTP_303_SEE_OTHER,
        )
