# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared helper functions for dashboard controllers."""

from __future__ import annotations

from pathlib import Path

from hop3.orm import App, AppRepository
from hop3.project.config import AppConfig


def get_app_or_none(db_session, app_name: str) -> App | None:
    """Get app from database by name."""
    app_repo = AppRepository(session=db_session)
    return app_repo.get_by_name(app_name)


def get_worker_count(app: App) -> int:
    """Get worker count for an app."""
    app_path = Path(app.app_path)
    if not app_path.exists():
        return 0

    try:
        config_obj = AppConfig.from_dir(app_path)
        return len(config_obj.workers)
    except Exception:
        return 0


def get_app_state_dict(app: App) -> str:
    """Convert app run state to string representation."""
    if hasattr(app.run_state, "name"):
        return app.run_state.name
    return str(app.run_state)


def get_addons_for_app(app: App) -> list[dict]:
    """Get list of addons attached to an app."""
    addons = []
    for credential in app.addon_credentials:
        addons.append({
            "addon_name": credential.addon_name,
            "addon_type": credential.addon_type,
            "created_at": credential.created_at.strftime("%Y-%m-%d %H:%M")
            if credential.created_at
            else "N/A",
        })
    return addons


def format_size(size_bytes: int) -> str:
    """Format size in bytes to human-readable string."""
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def is_service_var(var_name: str) -> bool:
    """Check if an environment variable is service-generated."""
    service_suffixes = [
        "_URL",
        "_HOST",
        "_PORT",
        "_USER",
        "_PASSWORD",
        "_DATABASE",
    ]
    return any(suffix in var_name.upper() for suffix in service_suffixes)
