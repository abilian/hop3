# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Root controller for redirecting to dashboard or login."""

from __future__ import annotations

from litestar import Controller, Request, get
from litestar.response import Redirect

from hop3 import config
from hop3.server.security.web_auth import current_identity


class RootController(Controller):
    """
    Root path controller.

    Handles the root path "/" and redirects to either dashboard or login.
    """

    path = "/"

    @get("/", sync_to_thread=False)
    def root_redirect(self, request: Request) -> Redirect:
        """
        Redirect root to the dashboard when authenticated, else to login.

        Auth is the stateless signed cookie (``current_identity``); there is no
        server-side session. ``HOP3_UNSAFE`` (testing) skips the check.

        Args:
            request: HTTP request

        Returns:
            Redirect to dashboard or login page
        """
        if config.HOP3_UNSAFE or current_identity(request):
            return Redirect(path="/dashboard")
        return Redirect(path="/auth/login")
