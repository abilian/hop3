# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Root controller for redirecting to dashboard or login."""

from __future__ import annotations

from typing import Any

from litestar import Controller, get
from litestar.response import Redirect

from hop3 import config


class RootController(Controller):
    """Root path controller.

    Handles the root path "/" and redirects to either dashboard or login.
    """

    path = "/"

    @get("/", sync_to_thread=False)
    def root_redirect(self, scope: Any) -> Redirect:
        """Redirect root to dashboard or login.

        Args:
            scope: ASGI scope for request context (dict-like object)

        Returns:
            Redirect to dashboard or login page
        """
        # If HOP3_UNSAFE is true (testing mode), skip authentication
        if config.HOP3_UNSAFE:
            return Redirect(path="/dashboard")

        # Check if auth middleware provided user
        if "user" not in scope:
            return Redirect(path="/auth/login")

        # Check authentication status
        if scope["user"].is_authenticated:
            return Redirect(path="/dashboard")

        return Redirect(path="/auth/login")
