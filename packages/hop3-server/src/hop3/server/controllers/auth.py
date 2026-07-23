# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Authentication controller for web dashboard."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from litestar import Controller, Request, get, post
from litestar.response import Redirect, Template

from hop3.orm.repositories import UserRepository
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session
from hop3.server.security.rate_limit import RateLimiter, RateLimitError
from hop3.server.security.tokens import validate_magic_token
from hop3.server.security.web_auth import (
    auth_cookie,
    clear_auth_cookie,
    current_identity,
)

if TYPE_CHECKING:
    from litestar.params import FromPath

# Module-level rate limiter shared across all AuthController instances.
# 5 attempts per IP per minute is enough for legitimate users (typos)
# and prevents brute force on credentials and magic links.
_AUTH_RATE_LIMITER = RateLimiter(max_requests=5, window_seconds=60.0)


# TCP peers we trust to have set X-Forwarded-For. hop3-server sits behind the
# platform reverse proxy (nginx) on the same host; a client connecting directly
# to the app port is never trusted to set XFF. Additional proxy IPs (e.g. an
# external load balancer) can be allow-listed via HOP3_TRUSTED_PROXIES.
_DEFAULT_TRUSTED_PROXIES: frozenset[str] = frozenset({"127.0.0.1", "::1"})


def _trusted_proxies() -> frozenset[str]:
    extra = os.environ.get("HOP3_TRUSTED_PROXIES", "")
    if not extra:
        return _DEFAULT_TRUSTED_PROXIES
    return _DEFAULT_TRUSTED_PROXIES | {
        ip.strip() for ip in extra.split(",") if ip.strip()
    }


def _client_ip(request: Request) -> str:
    """Client IP for rate limiting (audit H1, CWE-290).

    X-Forwarded-For is honored ONLY when the TCP peer is a trusted proxy
    (loopback by default; extend with HOP3_TRUSTED_PROXIES). Otherwise the
    header is fully client-controlled, so an unauthenticated attacker could
    send a fresh IP per request and cycle past the per-IP rate limiter.

    When the peer IS trusted, we take the *rightmost* XFF entry — the address
    our proxy appended ($proxy_add_x_forwarded_for) — not the leftmost, which a
    client can pre-seed with a spoofed value before the proxy appends the real
    peer.
    """
    peer = request.client.host if request.client else "unknown"
    if peer in _trusted_proxies():
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return peer


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
        # Already authenticated → straight to the dashboard.
        if current_identity(request):
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
        # Rate limit by client IP to prevent brute-force attacks
        try:
            _AUTH_RATE_LIMITER.check(_client_ip(request))
        except RateLimitError as e:
            return Redirect(
                path=f"/auth/login?error=Too many login attempts. Try again in {int(e.retry_after) + 1}s."
            )

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
            user_repo = UserRepository(session=db_session)

            # Look up the user
            user = user_repo.get_by_username(username)

            if not user or not user.active or not user.check_password(password):
                return Redirect(
                    path=f"/auth/login?error=Invalid username or password&username={username}"
                )

            # Update login tracking
            user.last_login_at = user.current_login_at
            user.current_login_at = datetime.now(timezone.utc)
            user.login_count += 1
            user_repo.update(user, auto_commit=True)
            username = user.username

        # Issue the signed auth cookie (stateless — survives restarts).
        return Redirect(path="/dashboard", cookies=[auth_cookie(username)])

    @get("/logout", sync_to_thread=False)
    def logout(self, request: Request) -> Redirect:
        """Handle logout: revoke the cookie's token, then clear the cookie.

        The dashboard cookie IS a full bearer token, so dropping it client-side
        is not enough — a separately-captured copy would stay valid for the
        token's full lifetime. We revoke it server-side (the same mechanism the
        CLI logout uses) so web and CLI logout are symmetric (audit 2026-06 C5).

        Args:
            request: HTTP request

        Returns:
            Redirect to login page
        """
        from hop3.server.security.tokens import (  # ruff:ignore[import-outside-top-level]
            revoke_jwt,
        )
        from hop3.server.security.web_auth import (  # ruff:ignore[import-outside-top-level]
            AUTH_COOKIE,
        )

        token = request.cookies.get(AUTH_COOKIE)
        if token:
            revoke_jwt(token, reason="web_logout")
        return Redirect(path="/auth/login", cookies=[clear_auth_cookie()])

    @get("/profile", guards=[auth_guard], sync_to_thread=False)
    def profile(self, request: Request) -> Template | Redirect:
        """Display user profile page.

        Args:
            request: HTTP request

        Returns:
            Template response with profile information or redirect to login
        """
        # Identity from the verified auth cookie (auth_guard already passed).
        identity = current_identity(request)
        username = identity.get("username") if identity else None
        if not username:
            # No valid credential — shouldn't happen past the guard, but clear
            # any stale cookie and send them back to login.
            return Redirect(path="/auth/login", cookies=[clear_auth_cookie()])

        # Get user from database
        with get_session() as db_session:
            user_repo = UserRepository(session=db_session)

            user = user_repo.get_by_username(username)

            if not user:
                # Credential names an unknown user — clear it.
                return Redirect(path="/auth/login", cookies=[clear_auth_cookie()])

            ctx = {
                "user": {
                    "username": user.username,
                    "display_name": user.username,  # Use username as display name
                    "email": user.email or "Not set",
                    "is_admin": user.is_admin,
                    "active": user.active,
                    "created_at": user.created_at,
                    "last_login_at": user.last_login_at,
                    "login_count": user.login_count,
                }
            }

        return Template(template_name="auth/profile.html", context=ctx)

    @get("/magic/{token:str}", sync_to_thread=False)
    def magic_login(self, request: Request, token: FromPath[str]) -> Redirect:
        """Handle magic link login.

        Magic links are single-use, short-lived tokens that allow passwordless
        login. They are generated via the auth magic-link command (typically
        accessed via SSH).

        Args:
            request: HTTP request
            token: Magic link token from URL

        Returns:
            Redirect to dashboard on success, or to login page with error
        """
        # Rate limit by client IP to prevent magic-link brute-force
        try:
            _AUTH_RATE_LIMITER.check(_client_ip(request))
        except RateLimitError as e:
            return Redirect(
                path=f"/auth/login?error=Too many login attempts. Try again in {int(e.retry_after) + 1}s."
            )

        # Validate the magic token (also marks it as used)
        token_info = validate_magic_token(token)

        if not token_info:
            return Redirect(
                path="/auth/login?error=Invalid or expired magic link. Please generate a new one."
            )

        username = token_info.get("username")
        if not username:
            return Redirect(path="/auth/login?error=Invalid magic link token.")

        # Get user from database and create session
        with get_session() as db_session:
            user_repo = UserRepository(session=db_session)

            user = user_repo.get_by_username(username)

            if not user:
                return Redirect(path="/auth/login?error=User not found.")

            if not user.active:
                return Redirect(path="/auth/login?error=User account is disabled.")

            # Update login tracking
            user.last_login_at = user.current_login_at
            user.current_login_at = datetime.now(timezone.utc)
            user.login_count += 1
            user_repo.update(user, auto_commit=True)
            username = user.username

        # Issue the signed auth cookie (stateless — survives restarts).
        return Redirect(path="/dashboard", cookies=[auth_cookie(username)])
