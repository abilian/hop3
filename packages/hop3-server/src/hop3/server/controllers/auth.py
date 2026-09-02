# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Authentication controller for web dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from litestar import Controller, Request, get, post
from litestar.response import Redirect, Template

from hop3.orm.repositories import UserRepository
from hop3.orm.security import burn_password_check
from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session
from hop3.server.security.proxy_headers import client_ip
from hop3.server.security.rate_limit import AUTH_RATE_LIMITER, RateLimitError
from hop3.server.security.tokens import validate_magic_token
from hop3.server.security.web_auth import (
    auth_cookie,
    clear_auth_cookie,
    cookie_would_be_dropped,
    current_identity,
)

if TYPE_CHECKING:
    from litestar.params import FromPath

# The limiter lives in hop3.server.security.rate_limit: the RPC `auth
# get-token` path verifies the same credentials and has to draw on the same
# budget, and a second instance here would have meant a second budget.

# Shown when the browser reached us over plain HTTP outside debug mode, where
# the `Secure` auth cookie is accepted and then never sent back.
INSECURE_TRANSPORT_ERROR = (
    "Can't sign in over plain HTTP: the session cookie is marked Secure, so "
    "your browser will discard it and the login would loop silently. Reach "
    "this server over HTTPS — set an admin domain with a certificate "
    "(hop3-deploy-server --admin-domain ...) — or set HOP3_DEBUG=true for "
    "local development."
)


class AuthController(Controller):
    """
    Authentication controller for web-based login.

    Handles login, logout, and profile pages for the dashboard.
    """

    path = "/auth"

    def _refuse_login(self, request: Request) -> Redirect | None:
        """
        The checks every credential-accepting route runs first, or None.

        Both routes that can issue an auth cookie -- the login form and
        magic-link redemption -- have to refuse an unusable transport and
        draw on the rate-limit budget, in that order and before touching the
        credential. Keeping the pair in one place is the point: security-model
        §2.2 is a catalogue of fixes applied to one call site and missed at its
        twin, and these two are twins.
        """
        if cookie_would_be_dropped(request):
            return Redirect(path=f"/auth/login?error={INSECURE_TRANSPORT_ERROR}")

        try:
            AUTH_RATE_LIMITER.check(client_ip(request))
        except RateLimitError as e:
            return Redirect(
                path=f"/auth/login?error=Too many login attempts. Try again in {int(e.retry_after) + 1}s."
            )
        return None

    @get("/login", sync_to_thread=False)
    def login_page(self, request: Request) -> Template | Redirect:
        """
        Display the login page.

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
            # Warn before they type a password, not after the login loops.
            "insecure_transport": cookie_would_be_dropped(request),
        }
        return Template(template_name="auth/login.html", context=ctx)

    @post("/login")
    async def login_submit(
        self,
        request: Request,
    ) -> Redirect:
        """
        Handle login form submission.

        Args:
            request: HTTP request

        Returns:
            Redirect to dashboard on success, or back to login on failure
        """
        # Refuse before verifying anything: over plain HTTP the credential
        # would be checked, the cookie issued, and then silently discarded by
        # the browser (security-model.md §3.7).
        if refusal := self._refuse_login(request):
            return refusal

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

            # All three failures must be indistinguishable, in *time* as well
            # as in the reply: short-circuiting before check_password answers
            # an unknown or disabled account measurably faster than a wrong
            # password, which enumerates valid usernames (CWE-204). Burn an
            # equivalent bcrypt round on the paths that skip the real one.
            # `hop3 auth login` (commands/auth.py) does the same; keep in step.
            invalid = Redirect(
                path=f"/auth/login?error=Invalid username or password&username={username}"
            )
            if not user:
                burn_password_check(password)
                return invalid
            if not user.active:
                burn_password_check(password)
                return invalid
            if not user.check_password(password):
                return invalid

            # Update login tracking
            user.last_login_at = user.current_login_at
            user.current_login_at = datetime.now(timezone.utc)
            user.login_count += 1
            user_repo.update(user, auto_commit=True)
            username = user.username

        # Issue the signed auth cookie (stateless — survives restarts).
        return Redirect(path="/dashboard", cookies=[auth_cookie(username)])

    @post("/logout")
    async def logout(self, request: Request) -> Redirect:
        """
        Handle logout: revoke the cookie's token, then clear the cookie.

        The dashboard cookie IS a full bearer token, so dropping it client-side
        is not enough — a separately-captured copy would stay valid for the
        token's full lifetime. We revoke it server-side (the same mechanism the
        CLI logout uses) so web and CLI logout are symmetric (audit 2026-06 C5).

        POST, not GET. `samesite=lax` deliberately sends the auth cookie on a
        cross-site *GET*, so while this was a link any page could log a user
        out by embedding it — the one state-changing GET that made the "every
        mutation is a POST" argument for having no CSRF token untrue
        (security-model.md §3.7). Impact was low (idempotent, no data loss);
        the reason to fix it is that the invariant has to hold to be worth
        anything.

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
        """
        Display user profile page.

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
        """
        Handle magic link login.

        Magic links are single-use, short-lived tokens that allow passwordless
        login. They are generated via the auth magic-link command (typically
        accessed via SSH).

        Args:
            request: HTTP request
            token: Magic link token from URL

        Returns:
            Redirect to dashboard on success, or to login page with error
        """
        # Runs *before* validating the token: `validate_magic_token` consumes
        # it, so an unusable transport would burn a single-use link to reach a
        # login that cannot hold its cookie.
        if refusal := self._refuse_login(request):
            return refusal

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

            # Both branches leave the link spent, by decision (F6, 2026-08-02):
            # neither condition is one the holder can fix inside the token's
            # 5-minute life, and a token presented once must not be replayable.
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
