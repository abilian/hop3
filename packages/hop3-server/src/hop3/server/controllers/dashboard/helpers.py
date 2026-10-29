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
from litestar.response import Redirect
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3.lib.logging import server_log
from hop3.orm import App, AppRepository
from hop3.orm.app import AppStateEnum
from hop3.project.config import AppConfig
from hop3.server.security.tokens import get_secret_key
from hop3.server.streaming import has_active_deploy

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session


# A mutation's outcome travels to the next page as a signed token, never as
# query text: a page that printed `?error=...` let any link put arbitrary words
# on an authenticated page (audit 2026-10). The token is bound to the page it
# was issued for and expires, so it cannot be transplanted or replayed later.
FLASH_PARAM = "flash"
_FLASH_AUDIENCE = "hop3-dashboard-flash"
_FLASH_TTL_SECONDS = 600
# The token rides in the URL: an error carrying a command's whole output would
# push it past the proxy's request-line limit (414), losing the very failure it
# was meant to show. The full text is in the server log, which every caller
# writes first.
_FLASH_TEXT_MAX = 1000
_FLASH_TRUNCATED = " [...] (truncated; the full error is in the server log)"


def run_mutation(
    db_session: Session, page: str, what: str, do: Callable[[], str], **context: str
) -> Redirect:
    """
    Run one dashboard mutation and report its real outcome on ``page``.

    ``do`` performs it and returns the success banner; ``what`` names it for
    the failure banner ("restart application 'x'"). These handlers used to
    ``print()`` the exception and redirect exactly as on success, so a failed
    restore was indistinguishable from a successful one: the fake success the
    fail-loud rule forbids. The reason now reaches the operator (a signed
    flash, so a crafted link cannot fake one) and the log.
    """
    try:
        message = do()
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        server_log.exception(
            "Dashboard action failed", action=what, error=str(e), **context
        )
        text = f"Failed to {what}: {type(e).__name__}: {e}"
        return Redirect(
            path=flash_url(page, ok=False, text=text), status_code=HTTP_303_SEE_OTHER
        )
    server_log.info("Dashboard action succeeded", action=what, **context)
    return Redirect(
        path=flash_url(page, ok=True, text=message), status_code=HTTP_303_SEE_OTHER
    )


def flash_url(path: str, *, ok: bool, text: str) -> str:
    """``path`` carrying a signed outcome (success or the real error) to show."""
    if len(text) > _FLASH_TEXT_MAX:
        text = text[:_FLASH_TEXT_MAX] + _FLASH_TRUNCATED
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
