# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Shared HTTP-vs-HTTPS policy for every reverse-proxy plugin.

An app that knows it is served over HTTPS (Hop3 tells it so via
``HOP3_PUBLIC_URL``, and its own config echoes that in a ``ROOT_URL`` or
equivalent) issues **Secure** session and CSRF cookies. A browser never sends
those back over plain HTTP, so an app reachable on both schemes looks healthy
while every login over HTTP silently fails — the error surfaces as "credentials
do not match", pointing at the password rather than the scheme.

So HTTPS-only is the default, and it must be the same default whichever proxy
is installed: the recipe declares intent once, in ``[deploy].allow-http``, and
every proxy honours it identically. Each proxy keeps its own legacy
``<PROXY>_HTTPS_ONLY`` env var as an explicit per-app override.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3.core.env import Env

#: Set by the deployer from ``[deploy].allow-http``.
ALLOW_HTTP_KEY = "HOP3_ALLOW_HTTP"


def should_redirect_to_https(env: Env, legacy_key: str) -> bool:
    """
    Should this proxy redirect plain HTTP to HTTPS?

    True unless the app opted into plain HTTP. An explicitly set
    ``legacy_key`` (e.g. ``NGINX_HTTPS_ONLY``) still wins, so an operator who
    set it before this default existed keeps the behaviour they configured.
    """
    if legacy_key in env:
        return env.get_bool(legacy_key)
    return not env.get_bool(ALLOW_HTTP_KEY)
