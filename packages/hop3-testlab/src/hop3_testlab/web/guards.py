# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Auth guard (mirrors hop3-server's session-cookie guard).

v1: a single admin, session-cookie auth. ``TESTLAB_UNSAFE=true`` bypasses it for
tests/dev (same shape as hop3-server's HOP3_UNSAFE). Bearer-token support can be
added later for a JSON API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from litestar.exceptions import NotAuthorizedException

from hop3_testlab.config import TestlabConfig

if TYPE_CHECKING:
    from litestar.connection import ASGIConnection
    from litestar.handlers.base import BaseRouteHandler


def auth_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    """Allow the request only if unsafe-mode is on or a user is logged in."""
    if TestlabConfig.get_instance().UNSAFE:
        return
    if connection.session.get("user_id"):
        return
    msg = "Authentication required"
    raise NotAuthorizedException(msg)
