# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Shared helper functions for dashboard controllers."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import jwt

from hop3.orm import App, AppRepository
from hop3.orm.app import AppStateEnum
from hop3.project.config import AppConfig
from hop3.server.security.tokens import get_secret_key
from hop3.server.streaming import has_active_deploy

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# A mutation's outcome travels to the next page as a signed token, never as
# query text: a page that printed `?error=...` let any link put arbitrary words
# on an authenticated page (audit 2026-10). The token is bound to the page it
# was issued for and expires, so it cannot be transplanted or replayed later.
FLASH_PARAM = "flash"
_FLASH_AUDIENCE = "hop3-dashboard-flash"
_FLASH_TTL_SECONDS = 600


def flash_url(path: str, *, ok: bool, text: str) -> str:
    """``path`` carrying a signed outcome (success or the real error) to show."""
    payload = {
        "aud": _FLASH_AUDIENCE,
        "path": path,
        "ok": ok,
        "text": text,
        "exp": int(time.time()) + _FLASH_TTL_SECONDS,
    }
    token = jwt.encode(payload, get_secret_key(), algorithm="HS256")
    return f"{path}?{urlencode({FLASH_PARAM: token})}"


def read_flash(token: str | None, path: str) -> dict | None:
    """The outcome a ``flash_url`` token carries for ``path``, or None."""
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, get_secret_key(), algorithms=["HS256"], audience=_FLASH_AUDIENCE
        )
    except jwt.InvalidTokenError:
        return None
    if payload.get("path") != path:
        return None
    return {"ok": bool(payload.get("ok")), "text": str(payload.get("text", ""))}


def get_app_or_none(db_session: Session, app_name: str) -> App | None:
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


def get_display_state(app: App) -> str:
    """
    The app's state as an operator reads it, including an in-flight deploy.

    ``run_state`` tracks the *process*, so an app whose build is still running
    reads STOPPED — indistinguishable from "it never started" through a build
    that can take minutes. A deploy in flight wins over that: report DEPLOYING.
    A running app keeps its state, so a redeploy of a live app still shows
    RUNNING rather than implying it went down.
    """
    state = get_app_state_dict(app)
    if state != AppStateEnum.RUNNING.name and has_active_deploy(app.name):
        return "DEPLOYING"
    return state


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
