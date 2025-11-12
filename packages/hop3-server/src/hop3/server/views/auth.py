# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Web-based authentication views for the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse

from hop3.orm import User
from hop3.server.lib.database import get_session
from hop3.server.singletons import router, templates

if TYPE_CHECKING:
    from starlette.requests import Request


@router.get("/auth/login")
def login_page(request: Request):
    """Display the login page.

    Args:
        request: The HTTP request

    Returns:
        Template response with login form
    """
    # If already authenticated, redirect to dashboard
    if request.user.is_authenticated:
        return RedirectResponse(url="/dashboard", status_code=302)

    ctx = {
        "error": request.query_params.get("error"),
        "username": request.query_params.get("username", ""),
    }
    return templates(request, "auth/login.html", ctx)


@router.post("/auth/login")
async def login_submit(request: Request):
    """Handle login form submission.

    Args:
        request: The HTTP request with form data

    Returns:
        Redirect to dashboard on success, or back to login on failure
    """
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    if not username or not password:
        return RedirectResponse(
            url=f"/auth/login?error=Please enter both username and password&username={username}",
            status_code=302,
        )

    # Get database session
    with get_session() as db_session:
        # Look up the user
        user = db_session.query(User).filter_by(username=username).first()

        if not user or not user.active or not user.check_password(password):
            return RedirectResponse(
                url=f"/auth/login?error=Invalid username or password&username={username}",
                status_code=302,
            )

        # Store user ID in session
        request.session["user_id"] = user.id
        request.session["username"] = user.username

        # Update login tracking
        user.last_login_at = user.current_login_at
        user.current_login_at = datetime.now(timezone.utc)
        user.login_count += 1
        db_session.commit()

    # Redirect to dashboard
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/auth/logout")
def logout(request: Request):
    """Handle logout.

    Args:
        request: The HTTP request

    Returns:
        Redirect to login page
    """
    # Clear session
    request.session.clear()

    # Redirect to login
    return RedirectResponse(url="/auth/login", status_code=302)


@router.get("/auth/profile")
def profile(request: Request):
    """Display user profile page.

    Args:
        request: The HTTP request

    Returns:
        Template response with profile information
    """
    # Require authentication
    if not request.user.is_authenticated:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Get user from database
    with get_session() as db_session:
        user = (
            db_session.query(User)
            .filter_by(username=request.user.username)
            .first()
        )

        if not user:
            # Session is invalid, clear it
            request.session.clear()
            return RedirectResponse(url="/auth/login", status_code=302)

        ctx = {
            "user": {
                "username": user.username,
                "display_name": user.display_name,
                "email": user.email or "Not set",
                "is_admin": user.is_admin,
                "active": user.active,
                "created_at": user.created_at,
                "last_login_at": user.last_login_at,
                "login_count": user.login_count,
            }
        }

    return templates(request, "auth/profile.html", ctx)
