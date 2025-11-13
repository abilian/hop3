# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Database helper functions for dashboard views."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from hop3.orm import App
from hop3.project.config import AppConfig

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_app_or_none(db_session: Session, app_name: str) -> App | None:
    """Get app from database by name.

    Args:
        db_session: Database session
        app_name: Application name

    Returns:
        App instance or None if not found
    """
    return db_session.query(App).filter_by(name=app_name).first()


def get_worker_count(app: App) -> int:
    """Get worker count for an app.

    Args:
        app: Application instance

    Returns:
        Number of workers configured
    """
    app_path = Path(app.app_path)
    if not app_path.exists():
        return 0

    try:
        config = AppConfig.from_dir(app_path)
        return len(config.workers)
    except Exception:
        return 0


def get_app_state_dict(app: App) -> dict:
    """Convert app run state to string representation.

    Args:
        app: Application instance

    Returns:
        State as string (name attribute or string representation)
    """
    if hasattr(app.run_state, "name"):
        return app.run_state.name
    return str(app.run_state)


def get_services_for_app(app: App) -> list[dict]:
    """Get list of services attached to an app.

    Args:
        app: Application instance

    Returns:
        List of service dicts with name, type, created_at
    """
    services = []
    for credential in app.service_credentials:
        services.append({
            "service_name": credential.service_name,
            "service_type": credential.service_type,
            "created_at": credential.created_at.strftime("%Y-%m-%d %H:%M")
            if credential.created_at
            else "N/A",
        })
    return services
