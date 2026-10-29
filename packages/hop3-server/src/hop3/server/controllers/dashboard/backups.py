# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# `@inject` resolves the handler annotations when it wraps them, so the types
# named in a handler signature are runtime imports.
# ruff:file-ignore[typing-only-first-party-import, typing-only-third-party-import]

"""
Dashboard backups controller.

Every handler reads manifests and archives or restores them, so the work runs
on a worker thread: the server has one worker, and on the event loop it would
freeze every other request (``backup_info`` checksums the whole archive).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, Request, get, post
from litestar.params import FromPath, FromQuery
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy.orm import Session

from hop3.core.backup import BackupManager, BackupManifest, UnreadableBackup
from hop3.core.roles import Role
from hop3.lib.logging import server_log
from hop3.orm.repositories import BackupRepository
from hop3.server.guards import RoleGuard

from .helpers import FLASH_PARAM, flash_url, format_size, read_flash

if TYPE_CHECKING:
    from collections.abc import Callable

BACKUPS_PAGE = "/dashboard/backups"
PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


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

    path = BACKUPS_PAGE
    guards = [RoleGuard(Role.VIEWER)]  # ruff:ignore[mutable-class-default]

    @get("/")
    @inject
    async def dashboard_backups(
        self,
        request: Request,
        manager: FromDishka[BackupManager],
        backup_repo: FromDishka[BackupRepository],
        offset: FromQuery[int] = 0,
        limit: FromQuery[int] = PAGE_SIZE,
    ) -> Template | Redirect:
        """Display one page of backups, most recent first."""
        flash = read_flash(request.query_params.get(FLASH_PARAM), request.url.path)
        offset = max(offset, 0)
        limit = min(max(limit, 1), MAX_PAGE_SIZE)
        return await anyio.to_thread.run_sync(
            self._list, manager, backup_repo, offset, limit, flash
        )

    @staticmethod
    def _list(
        manager: BackupManager,
        backup_repo: BackupRepository,
        offset: int,
        limit: int,
        flash: dict | None,
    ) -> Template:
        backups = [
            _backup_row(entry)
            for entry in manager.list_backups(app_name=None, limit=limit, offset=offset)
        ]

        total = backup_repo.count()
        ctx = {
            "backups": backups,
            "flash": flash,
            "page": {
                "first": offset + 1 if backups else 0,
                "last": offset + len(backups),
                "total": total,
                "limit": limit,
                "prev": max(offset - limit, 0) if offset > 0 else None,
                "next": offset + limit if offset + limit < total else None,
            },
        }
        return Template(template_name="dashboard/backups.html", context=ctx)

    @get("/{backup_id:str}/info")
    @inject
    async def backup_info(
        self, backup_id: FromPath[str], manager: FromDishka[BackupManager]
    ) -> Template | Redirect:
        """Display detailed backup information, with every checksum verified."""
        return await anyio.to_thread.run_sync(self._info, manager, backup_id)

    @staticmethod
    def _info(manager: BackupManager, backup_id: str) -> Template | Redirect:
        try:
            manifest = manager.get_backup_info(backup_id)
            verification = manager.verify_backup(backup_id)
        except FileNotFoundError:
            return Redirect(path=BACKUPS_PAGE)
        except Exception as e:
            server_log.exception(
                "Could not read backup info", backup_id=backup_id, error=str(e)
            )
            text = f"Could not read backup {backup_id}: {type(e).__name__}: {e}"
            return Redirect(
                path=flash_url(BACKUPS_PAGE, ok=False, text=text),
                status_code=HTTP_303_SEE_OTHER,
            )

        checksums = [
            {
                "filename": filename,
                "checksum": checksum,
                "valid": verification.get(filename, False),
            }
            for filename, checksum in manifest.checksums.items()
        ]
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
                "all_valid": all(verification.values()),
            },
        }
        return Template(template_name="dashboard/backup_info.html", context=ctx)

    @post(
        "/{backup_id:str}/restore",
        status_code=303,
        guards=[RoleGuard(Role.DEPLOYER)],
    )
    @inject
    async def backup_restore(
        self,
        backup_id: FromPath[str],
        manager: FromDishka[BackupManager],
        db_session: FromDishka[Session],
    ) -> Redirect:
        """Restore a backup."""

        def _restore() -> str:
            manifest = manager.get_backup_info(backup_id)
            manager.restore_backup(backup_id)
            return f"Restored backup {backup_id} to {manifest.app_name}"

        return await anyio.to_thread.run_sync(
            _run_backup_action, db_session, backup_id, "restore", _restore
        )

    @post(
        "/{backup_id:str}/delete",
        status_code=303,
        guards=[RoleGuard(Role.DEPLOYER)],
    )
    @inject
    async def backup_delete(
        self,
        backup_id: FromPath[str],
        manager: FromDishka[BackupManager],
        db_session: FromDishka[Session],
    ) -> Redirect:
        """Delete a backup."""

        def _delete() -> str:
            manager.delete_backup(backup_id)
            return f"Deleted backup {backup_id}"

        return await anyio.to_thread.run_sync(
            _run_backup_action, db_session, backup_id, "delete", _delete
        )


def _run_backup_action(
    db_session: Session, backup_id: str, action: str, do: Callable[[], str]
) -> Redirect:
    """
    Run one backup mutation and report its real outcome to the browser.

    A failed **restore** used to be pixel-identical to a successful one: the
    exception went to the server's stdout via `print()` and the browser got the
    same redirect either way. For an operation whose whole purpose is
    recovering data, silently reporting success is the worst available failure
    mode, and the project's fail-loud rule forbids it outright. The outcome
    travels as a signed flash, so a crafted link cannot fake one.
    """
    try:
        message = do()
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        server_log.exception(
            "Dashboard backup action failed",
            backup_id=backup_id,
            action=action,
            error=str(e),
        )
        text = f"Failed to {action} backup {backup_id}: {type(e).__name__}: {e}"
        return Redirect(
            path=flash_url(BACKUPS_PAGE, ok=False, text=text),
            status_code=HTTP_303_SEE_OTHER,
        )
    server_log.info("Backup action succeeded", backup_id=backup_id, action=action)
    return Redirect(
        path=flash_url(BACKUPS_PAGE, ok=True, text=message),
        status_code=HTTP_303_SEE_OTHER,
    )


def _backup_row(entry: BackupManifest | UnreadableBackup) -> dict:
    """One table row; an unreadable backup is listed with its reason."""
    if isinstance(entry, UnreadableBackup):
        return {
            "backup_id": entry.backup_id,
            "app_name": entry.app_name,
            "created": _format_backup_datetime(entry.backup_id, ""),
            "unreadable": entry.reason,
        }
    addons_list = [s["name"] for s in entry.addons]
    return {
        "backup_id": entry.backup_id,
        "app_name": entry.app_name,
        "created": _format_backup_datetime(entry.backup_id, entry.created_at),
        "size": format_size(entry.size_bytes),
        "addons_count": len(entry.addons),
        "addons": ", ".join(addons_list) if addons_list else "None",
    }
