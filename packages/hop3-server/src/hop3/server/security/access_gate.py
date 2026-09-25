# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The access gate's decisions and credentials (ADR 062).

Two credentials carry a sign-in from the admin domain to an app's host, where
the admin cookie never goes: a one-time code, minted when an admin-domain
session asks for the app and redeemed on the app's host within a minute, and
the gate cookie the redemption sets. The cookie names the app it was minted
for and the admin session behind it, so it is refused by every other app and
dies with that session.

Which paths are public:

A public path is reachable without signing in, so the path the gate matches
must be the path the app routes (ADR 050 Security invariant 2). The gate only
ever grants: a path it cannot read unambiguously is treated as not public, and
the request needs a sign-in. That makes normalization a single percent-decode
of a path that has nothing to resolve: dot segments, empty segments, encoded
separators and double encoding all mean "ambiguous", never "public".
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote, urlsplit

import jwt
from sqlalchemy import select

from hop3.config import config
from hop3.orm import App, get_session_factory
from hop3.server.security.authorization import Account, lookup_account
from hop3.server.security.tokens import get_secret_key, is_token_revoked

if TYPE_CHECKING:
    from hop3.core.roles import Role

#: Host-only, Secure and Path=/, by the browser's `__Host-` rules.
GATE_COOKIE = "__Host-hop3_gate"
CODE_LIFETIME_SECONDS = 60

# After one decode, any of these means the app and the gate could read the
# path differently: a second encoding layer, an encoded or doubled separator,
# a backslash some servers treat as a slash, or a control character.
_AMBIGUOUS = re.compile(r"%[0-9A-Fa-f]{2}|//|\\|[\x00-\x1f\x7f]")
_ENCODED_SEPARATOR = re.compile(r"%(2[Ff]|5[Cc])")


def canonical_path(request_uri: str) -> str | None:
    """
    The path of ``request_uri`` as the gate matches it, or None if ambiguous.

    ``request_uri`` is the request line's target, query string included.
    """
    path = request_uri.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/") or _ENCODED_SEPARATOR.search(path):
        return None
    decoded = unquote(path)
    if _AMBIGUOUS.search(decoded):
        return None
    if any(segment in {".", ".."} for segment in decoded.split("/")):
        return None
    return decoded


def is_public(request_uri: str, public_paths: list[str]) -> bool:
    """True when the request's path full-matches one of ``public_paths``."""
    path = canonical_path(request_uri)
    if path is None:
        return False
    return any(re.fullmatch(pattern, path) for pattern in public_paths)


@dataclass(frozen=True, slots=True)
class Grant:
    """A signed-in admin-domain session, handed to one app."""

    app_name: str
    username: str
    #: The admin session's token id; revoking it signs the user out of the app.
    session_id: str
    #: The admin session's expiry (epoch seconds); the gate cookie shares it.
    expires_at: int


@dataclass(frozen=True, slots=True)
class _Pending:
    grant: Grant
    deadline: float


class _CodeStore:
    """
    One-time codes, in this process.

    ponytail: in memory, which holds because the server runs one worker; a
    code dies with a restart, and its user signs in again.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, _Pending] = {}

    def mint(self, grant: Grant) -> str:
        code = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._pending = {c: p for c, p in self._pending.items() if p.deadline > now}
            self._pending[code] = _Pending(grant, now + CODE_LIFETIME_SECONDS)
        return code

    def redeem(self, code: str, app_name: str) -> Grant | None:
        with self._lock:
            pending = self._pending.pop(code, None)
        if pending is None or pending.deadline <= time.monotonic():
            return None
        if pending.grant.app_name != app_name:
            return None
        return pending.grant


_codes = _CodeStore()


def mint_code(grant: Grant) -> str:
    """A code the app's host redeems once, within a minute, for ``grant``."""
    return _codes.mint(grant)


def redeem_code(code: str, app_name: str) -> Grant | None:
    """The grant behind ``code`` if it is live and was minted for ``app_name``."""
    return _codes.redeem(code, app_name)


def _audience(app_name: str) -> str:
    return f"hop3-gate:{app_name}"


def gate_token(grant: Grant) -> str:
    """The gate cookie's value: signed, for one app, bound to one session."""
    payload = {
        "sub": grant.username,
        "aud": _audience(grant.app_name),
        "sid": grant.session_id,
        "iat": int(time.time()),
        "exp": grant.expires_at,
    }
    return jwt.encode(payload, get_secret_key(), algorithm="HS256")


def read_gate_token(token: str, app_name: str) -> str | None:
    """
    The username a gate cookie names for ``app_name``, or None.

    None when the signature, the audience or the expiry is wrong, or when the
    admin session that minted it has been revoked (signed out).
    """
    try:
        payload = jwt.decode(
            token,
            get_secret_key(),
            algorithms=["HS256"],
            audience=_audience(app_name),
            options={"require": ["sub", "aud", "sid", "exp"]},
        )
    except jwt.InvalidTokenError:
        return None
    if is_token_revoked(payload["sid"]):
        return None
    return payload["sub"]


@dataclass(frozen=True, slots=True)
class Policy:
    """An app's ``[access]``, as recorded at its last deploy."""

    role: Role
    public_paths: list[str]


def load_policy(app_name: str) -> Policy | None:
    """The gate policy of ``app_name``, or None when the app has no gate."""
    with get_session_factory()() as db_session:
        app = db_session.scalar(select(App).where(App.name == app_name))
        if app is None or app.access_role is None:
            return None
        return Policy(role=app.access_role, public_paths=list(app.access_public_paths))


def gated_app_for_host(host: str) -> str | None:
    """The gated app that answers on ``host``, or None."""
    with get_session_factory()() as db_session:
        gated = db_session.scalars(select(App).where(App.access_role.is_not(None)))
        for app in gated:
            if host in app.hostname.replace(",", " ").split():
                return app.name
    return None


@dataclass(frozen=True, slots=True)
class Admit:
    #: Who is asking, when the app may be told: signed in with enough role.
    account: Account | None


@dataclass(frozen=True, slots=True)
class SignIn:
    pass


@dataclass(frozen=True, slots=True)
class Forbid:
    account: Account


Verdict = Admit | SignIn | Forbid


def decide(policy: Policy, request_uri: str, account: Account | None) -> Verdict:
    """
    Whether the gate lets a request through, and as whom.

    ``account`` is the one the request's gate cookie names, if any. Its role is
    read now, so a demotion or a disabled account takes effect at once.
    """
    if account is not None and not account.active:
        account = None
    if account is not None and account.role.includes(policy.role):
        return Admit(account)
    if is_public(request_uri, policy.public_paths):
        return Admit(None)
    if account is not None:
        return Forbid(account)
    return SignIn()


def account_for(gate_cookie: str, app_name: str) -> Account | None:
    """The account a gate cookie names for ``app_name``, if it is valid."""
    if not gate_cookie:
        return None
    username = read_gate_token(gate_cookie, app_name)
    return lookup_account(username) if username else None


def split_gate_cookie(cookie_header: str) -> tuple[str, str]:
    """
    ``(gate cookie value, the other cookies)`` from a ``Cookie`` header.

    The second part is what the app receives: the gate cookie never reaches it.
    """
    gate, others = "", []
    for pair in cookie_header.split(";"):
        name, _, value = pair.strip().partition("=")
        if not name:
            continue
        if name == GATE_COOKIE:
            gate = value
        else:
            others.append(pair.strip())
    return gate, "; ".join(others)


def sign_in_url(host: str, request_uri: str) -> str:
    """The admin-domain sign-in that comes back to ``request_uri`` on ``host``."""
    next_url = quote(f"https://{host}{request_uri}", safe="")
    return f"https://{config.ADMIN_DOMAIN}/auth/login?next={next_url}"


def same_host_path(next_path: str) -> str:
    """``next_path`` if it is a path on this host, else ``/``."""
    parts = urlsplit(next_path)
    if parts.scheme or parts.netloc or not next_path.startswith("/"):
        return "/"
    if next_path.startswith("//") or "\\" in next_path:
        return "/"
    return next_path


def continue_to(
    next_url: str, username: str, session_id: str | None, expires_at: int
) -> str | None:
    """
    Where a sign-in continues when the login page was given ``next_url``.

    A path on the admin domain is followed as is. A gated app's URL becomes
    that app's callback, carrying a one-time code for this session: that is
    how the sign-in crosses to a host the admin cookie never reaches. Anything
    else, a foreign host above all, is dropped (None: the landing page).
    """
    target = urlsplit(next_url)
    if not target.netloc:
        return next_url if next_url and same_host_path(next_url) == next_url else None
    if target.scheme != "https" or not target.hostname or target.username:
        return None
    path = same_host_path(target.path + (f"?{target.query}" if target.query else ""))
    if target.hostname == config.ADMIN_DOMAIN:
        return path
    app_name = gated_app_for_host(target.hostname)
    if app_name is None or not session_id:
        return None
    code = mint_code(Grant(app_name, username, session_id, expires_at))
    host = target.hostname + (f":{target.port}" if target.port else "")
    return f"https://{host}/_hop3/auth/callback?code={code}&next={quote(path, safe='')}"
