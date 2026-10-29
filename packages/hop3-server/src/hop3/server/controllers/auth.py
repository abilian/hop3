# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Authentication controller for web dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

import anyio
from dishka.integrations.litestar import FromDishka, inject
from litestar import Controller, Request, get, post

# Runtime imports: `@inject` resolves the handler annotations when it wraps them.
from litestar.params import FromPath  # ruff:ignore[typing-only-third-party-import]
from litestar.response import Redirect, Template

from hop3.config import config
from hop3.core.roles import Role
from hop3.orm.repositories import (  # ruff:ignore[typing-only-first-party-import]
    UserRepository,
)
from hop3.orm.security import User, burn_password_check
from hop3.server.guards import RoleGuard
from hop3.server.security.access_gate import continue_to
from hop3.server.security.authorization import lookup_account
from hop3.server.security.proxy_headers import client_ip
from hop3.server.security.rate_limit import AUTH_RATE_LIMITER, RateLimitError
from hop3.server.security.tokens import (
    revoke_jwt,
    validate_magic_token,
    validate_token,
)
from hop3.server.security.web_auth import (
    AUTH_COOKIE,
    auth_cookie,
    cookie_would_be_dropped,
    current_identity,
    expired_auth_cookie,
    issue_web_token,
)

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


# What the login page may say, by code. The page shows only these: an `?error=`
# carrying free text let any link print its own words on the sign-in page.
LOGIN_ERRORS = {
    "insecure_transport": INSECURE_TRANSPORT_ERROR,
    "rate_limited": "Too many login attempts. Try again in {retry}.",
    "missing_credentials": "Please enter both username and password",
    "invalid_credentials": "Invalid username or password",
    "magic_link_invalid": "Invalid or expired magic link. Please generate a new one.",
    "magic_link_malformed": "Invalid magic link token.",
    "magic_link_unknown_user": "User not found.",
    "magic_link_disabled": "User account is disabled.",
}


def login_page_url(
    error: str,
    username: str = "",
    next_url: str = "",
    state: str = "",
    retry: int = 0,
) -> str:
    """The login page again, with an error code, keeping what the user typed."""
    if error not in LOGIN_ERRORS:
        msg = f"Unknown login error code {error!r}; add it to LOGIN_ERRORS"
        raise ValueError(msg)
    params = {
        "error": error,
        "username": username,
        "next": next_url,
        "state": state,
        "retry": str(retry) if retry else "",
    }
    return "/auth/login?" + urlencode({k: v for k, v in params.items() if v})


def login_error_message(code: str | None, retry: str | None) -> str | None:
    """The message for a login error code; None for no code or an unknown one."""
    message = LOGIN_ERRORS.get(code or "")
    if message is None:
        return None
    seconds = int(retry) if retry and retry.isdigit() else 0
    return message.format(retry=f"{seconds}s" if seconds else "a moment")


def landing_page(role: Role) -> str:
    """
    Where a signed-in account lands: the dashboard, or its profile.

    A ``member`` can open no dashboard page (ADR 061 §4), so sending it to
    ``/dashboard`` would greet every sign-in with a refusal.
    """
    return "/dashboard" if role.includes(Role.VIEWER) else "/auth/profile"


class AuthController(Controller):
    """
    Authentication controller for web-based login.

    Handles login, logout, and profile pages for the dashboard.
    """

    path = "/auth"

    def _signed_in(
        self, username: str, role: Role, next_url: str, state: str
    ) -> Redirect:
        """
        End a sign-in: set the session cookie, then go where ``next`` leads.

        A gated app's ``next`` continues through its callback with a one-time
        code bound to this new session (ADR 062); anything else lands on the
        account's own page.
        """
        token = issue_web_token(username)
        return Redirect(
            path=self._destination(validate_token(token), role, next_url, state),
            cookies=[auth_cookie(token)],
        )

    @staticmethod
    def _destination(
        session: dict | None, role: Role, next_url: str, state: str
    ) -> str:
        if session and next_url:
            onward = continue_to(
                next_url,
                session["username"],
                session["token_id"],
                int(session["expires_at"]),
                state,
            )
            if onward:
                return onward
        return landing_page(role)

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
            return Redirect(path=login_page_url("insecure_transport"))

        try:
            AUTH_RATE_LIMITER.check(client_ip(request))
        except RateLimitError as e:
            return Redirect(
                path=login_page_url("rate_limited", retry=int(e.retry_after) + 1)
            )
        return None

    @get("/login", sync_to_thread=True)
    def login_page(self, request: Request) -> Template | Redirect:
        """
        Display the login page.

        Args:
            request: HTTP request

        Returns:
            Template response with login form or redirect if already authenticated
        """
        # Already signed in → the landing page. Only for an account that still
        # works: a cookie naming a deleted or disabled account would otherwise
        # bounce between here and a guard that refuses it, forever.
        next_url = request.query_params.get("next", "")
        state = request.query_params.get("state", "")
        if identity := current_identity(request):
            account = lookup_account(str(identity.get("username", "")))
            if account and account.active:
                return Redirect(
                    path=self._destination(identity, account.role, next_url, state)
                )

        ctx = {
            "error": login_error_message(
                request.query_params.get("error"), request.query_params.get("retry")
            ),
            "username": request.query_params.get("username", ""),
            # Warn before they type a password, not after the login loops.
            "insecure_transport": cookie_would_be_dropped(request),
            # The passwordless way in, for the operator who never held the
            # generated admin password. The server's own configured domain, not
            # `request.url.hostname` — the Host header is the caller's to choose
            # and this string is a command we are telling someone to run.
            "admin_domain": config.ADMIN_DOMAIN,
            "next": next_url,
            "state": state,
        }
        return Template(template_name="auth/login.html", context=ctx)

    @post("/login")
    @inject
    async def login_submit(
        self, request: Request, user_repo: FromDishka[UserRepository]
    ) -> Redirect:
        """
        Handle login form submission.

        Args:
            request: HTTP request
            user_repo: The request's user repository

        Returns:
            Redirect to dashboard on success, or back to login on failure
        """
        # Refuse before verifying anything: over plain HTTP the credential
        # would be checked, the cookie issued, and then silently discarded by
        # the browser (security-model.md §3.7).
        if refusal := self._refuse_login(request):
            return refusal

        form_data = await request.form()
        # bcrypt and the database, on a worker thread: the loop serves every
        # other request meanwhile.
        return await anyio.to_thread.run_sync(
            self._check_credentials,
            user_repo,
            form_data.get("username", ""),
            form_data.get("password", ""),
            form_data.get("next", ""),
            form_data.get("state", ""),
        )

    def _check_credentials(
        self,
        user_repo: UserRepository,
        username: str,
        password: str,
        next_url: str,
        state: str,
    ) -> Redirect:
        if not username or not password:
            return Redirect(
                path=login_page_url("missing_credentials", username, next_url, state)
            )

        user = user_repo.get_by_username(username)

        # All three failures must be indistinguishable, in *time* as well as
        # in the reply: short-circuiting before check_password answers an
        # unknown or disabled account measurably faster than a wrong password,
        # which enumerates valid usernames (CWE-204). Burn an equivalent bcrypt
        # round on the paths that skip the real one. `hop3 auth login`
        # (commands/auth.py) does the same; keep in step.
        invalid = Redirect(
            path=login_page_url("invalid_credentials", username, next_url, state)
        )
        if not user:
            burn_password_check(password)
            return invalid
        if not user.active:
            burn_password_check(password)
            return invalid
        if not user.check_password(password):
            return invalid

        _record_login(user_repo, user)
        # Issue the signed auth cookie (stateless — survives restarts).
        return self._signed_in(user.username, user.role, next_url, state)

    @post("/logout", sync_to_thread=True)
    def logout(self, request: Request) -> Redirect:
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
        token = request.cookies.get(AUTH_COOKIE)
        if token:
            revoke_jwt(token, reason="web_logout")
        return Redirect(path="/auth/login", cookies=[expired_auth_cookie()])

    @get("/profile", guards=[RoleGuard(Role.MEMBER)])
    @inject
    async def profile(
        self, request: Request, user_repo: FromDishka[UserRepository]
    ) -> Template | Redirect:
        """
        Display user profile page.

        Args:
            request: HTTP request
            user_repo: The request's user repository

        Returns:
            Template response with profile information or redirect to login
        """
        return await anyio.to_thread.run_sync(self._profile, request, user_repo)

    @staticmethod
    def _profile(request: Request, user_repo: UserRepository) -> Template | Redirect:
        # Identity from the verified auth cookie (the role guard already passed).
        identity = current_identity(request)
        username = identity.get("username") if identity else None
        if not username:
            # No valid credential — shouldn't happen past the guard, but clear
            # any stale cookie and send them back to login.
            return Redirect(path="/auth/login", cookies=[expired_auth_cookie()])

        user = user_repo.get_by_username(username)
        if not user:
            # Credential names an unknown user — clear it.
            return Redirect(path="/auth/login", cookies=[expired_auth_cookie()])

        ctx = {
            "user": {
                "username": user.username,
                "display_name": user.username,  # Use username as display name
                "email": user.email or "Not set",
                "is_admin": user.is_admin,
                "role": user.role.value,
                "active": user.active,
                "created_at": user.created_at,
                "last_login_at": user.last_login_at,
                "login_count": user.login_count,
            }
        }
        return Template(template_name="auth/profile.html", context=ctx)

    @get("/magic/{token:str}")
    @inject
    async def magic_login(
        self,
        request: Request,
        token: FromPath[str],
        user_repo: FromDishka[UserRepository],
    ) -> Redirect:
        """
        Handle magic link login.

        Magic links are single-use, short-lived tokens that allow passwordless
        login. They are generated via the auth magic-link command (typically
        accessed via SSH).

        Args:
            request: HTTP request
            token: Magic link token from URL
            user_repo: The request's user repository

        Returns:
            Redirect to dashboard on success, or to login page with error
        """
        # Runs *before* validating the token: `validate_magic_token` consumes
        # it, so an unusable transport would burn a single-use link to reach a
        # login that cannot hold its cookie.
        if refusal := self._refuse_login(request):
            return refusal
        return await anyio.to_thread.run_sync(
            self._redeem_magic_link,
            user_repo,
            token,
            request.query_params.get("next", ""),
            request.query_params.get("state", ""),
        )

    def _redeem_magic_link(
        self, user_repo: UserRepository, token: str, next_url: str, state: str
    ) -> Redirect:
        # Validate the magic token (also marks it as used)
        token_info = validate_magic_token(token)
        if not token_info:
            return Redirect(path=login_page_url("magic_link_invalid"))

        username = token_info.get("username")
        if not username:
            return Redirect(path=login_page_url("magic_link_malformed"))

        user = user_repo.get_by_username(username)
        # Both branches leave the link spent, by decision (F6, 2026-08-02):
        # neither condition is one the holder can fix inside the token's
        # 5-minute life, and a token presented once must not be replayable.
        if not user:
            return Redirect(path=login_page_url("magic_link_unknown_user"))
        if not user.active:
            return Redirect(path=login_page_url("magic_link_disabled"))

        _record_login(user_repo, user)
        # Issue the signed auth cookie (stateless — survives restarts).
        return self._signed_in(user.username, user.role, next_url, state)


def _record_login(user_repo: UserRepository, user: User) -> None:
    """Stamp a successful sign-in on the account, committed before we answer."""
    user.last_login_at = user.current_login_at
    user.current_login_at = datetime.now(timezone.utc)
    user.login_count += 1
    user_repo.update(user, auto_commit=True)
