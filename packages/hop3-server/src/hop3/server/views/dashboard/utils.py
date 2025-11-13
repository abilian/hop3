# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for dashboard views."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse

from hop3 import config

if TYPE_CHECKING:
    from starlette.requests import Request


def is_authenticated(request: Request) -> bool:
    """Check if user is authenticated, handling cases where auth middleware is not installed.

    Args:
        request: The HTTP request

    Returns:
        True if authenticated or in unsafe mode, False otherwise
    """
    # If HOP3_UNSAFE is true (testing mode), skip authentication
    if config.HOP3_UNSAFE:
        return True

    # Check if auth middleware is installed
    if "user" not in request.scope:
        # No auth middleware installed, default to unauthenticated
        return False

    # Auth middleware is installed, check authentication status
    return request.user.is_authenticated


def require_auth(func: Callable) -> Callable:
    """Decorator to require authentication for a view.

    Supports both sync and async view functions.

    Args:
        func: View function to wrap

    Returns:
        Wrapped function that checks authentication
    """
    import asyncio

    if asyncio.iscoroutinefunction(func):
        # Async function wrapper
        @wraps(func)
        async def async_wrapper(request: Request, *args, **kwargs):
            if not is_authenticated(request):
                return RedirectResponse(url="/auth/login", status_code=302)
            return await func(request, *args, **kwargs)

        return async_wrapper
    # Sync function wrapper

    @wraps(func)
    def sync_wrapper(request: Request, *args, **kwargs):
        if not is_authenticated(request):
            return RedirectResponse(url="/auth/login", status_code=302)
        return func(request, *args, **kwargs)

    return sync_wrapper


def format_size(size_bytes: int) -> str:
    """Format size in bytes to human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string like "1.5 MB"
    """
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_backup_datetime(backup_id: str, created_at: str) -> str:
    """Extract and format datetime from backup ID.

    Args:
        backup_id: Backup ID in format YYYYMMDD_HHMMSS_random
        created_at: Fallback created_at string

    Returns:
        Formatted datetime string
    """
    # Extract date from backup_id (YYYYMMDD_HHMMSS_random)
    backup_id_parts = backup_id.split("_")
    if len(backup_id_parts) >= 2:
        date_str = backup_id_parts[0]
        time_str = backup_id_parts[1]
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
    return created_at


def is_service_var(var_name: str) -> bool:
    """Check if an environment variable is service-generated.

    Args:
        var_name: Variable name to check

    Returns:
        True if this appears to be a service variable
    """
    service_suffixes = [
        "_URL",
        "_HOST",
        "_PORT",
        "_USER",
        "_PASSWORD",
        "_DATABASE",
    ]
    return any(suffix in var_name.upper() for suffix in service_suffixes)
