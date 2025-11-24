# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Authentication controller for web dashboard."""

from __future__ import annotations

from datetime import datetime, timezone

from litestar import Controller, Request, get, post
from litestar.response import Redirect, Template

from hop3.orm import User
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session


class AuthController(Controller):
    """Authentication controller for web-based login.

    Handles login, logout, and profile pages for the dashboard.
    """

    path = "/auth"

    @get("/login", sync_to_thread=False)
    def login_page(self, request: Request) -> Template | Redirect:
        """Display the login page.

        Args:
            request: HTTP request

        Returns:
            Template response with login form or redirect if already authenticated
        """
        # Check if user is authenticated via session
        if request.session.get("user_id"):
            return Redirect(path="/dashboard")

        ctx = {
            "error": request.query_params.get("error"),
            "username": request.query_params.get("username", ""),
        }
        return Template(template_name="auth/login.html", context=ctx)

    @post("/login")
    async def login_submit(
        self,
        request: Request,
    ) -> Redirect:
        """Handle login form submission.

        Args:
            request: HTTP request

        Returns:
            Redirect to dashboard on success, or back to login on failure
        """
        # Get form data directly from request
        form_data = await request.form()
        username = form_data.get("username", "")
        password = form_data.get("password", "")

        if not username or not password:
            return Redirect(
                path=f"/auth/login?error=Please enter both username and password&username={username}"
            )

        # Get database session
        with get_session() as db_session:
            # Look up the user
            user = db_session.query(User).filter_by(username=username).first()

            if not user or not user.active or not user.check_password(password):
                return Redirect(
                    path=f"/auth/login?error=Invalid username or password&username={username}"
                )

            # Store user ID in session using Litestar's session API
            request.set_session({"user_id": user.id, "username": user.username})

            # Update login tracking
            user.last_login_at = user.current_login_at
            user.current_login_at = datetime.now(timezone.utc)
            user.login_count += 1
            db_session.commit()

        # Redirect to dashboard
        return Redirect(path="/dashboard")

    @get("/logout", sync_to_thread=False)
    def logout(self, request: Request) -> Redirect:
        """Handle logout.

        Args:
            request: HTTP request

        Returns:
            Redirect to login page
        """
        # Clear session using Litestar's session API
        request.clear_session()

        # Redirect to login
        return Redirect(path="/auth/login")

    @get("/profile", guards=[auth_guard], sync_to_thread=False)
    def profile(self, request: Request) -> Template | Redirect:
        """Display user profile page.

        Args:
            request: HTTP request

        Returns:
            Template response with profile information or redirect to login
        """
        # Get username from session (auth_guard ensures user_id exists)
        username = request.session.get("username")
        if not username:
            # Session exists but no username - shouldn't happen, but handle it
            request.clear_session()
            return Redirect(path="/auth/login")

        # Get user from database
        with get_session() as db_session:
            user = db_session.query(User).filter_by(username=username).first()

            if not user:
                # Session is invalid, clear it
                request.clear_session()
                return Redirect(path="/auth/login")

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

        return Template(template_name="auth/profile.html", context=ctx)
