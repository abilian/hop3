# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import os
import secrets
import warnings
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import (
    AuthenticationMiddleware as StarletteAuthMiddleware,
)
from starlette.middleware.sessions import SessionMiddleware

from .lib.scanner import scan_package
from .middleware.auth import SessionAuthBackend, on_auth_error
from .singletons import router

if TYPE_CHECKING:
    pass

DEBUG = True


def create_app():
    scan_package("hop3.server.views")
    routes = list(router)

    # Add authentication middleware if enabled
    # Read from environment to support test fixtures that set env vars
    enable_auth = os.environ.get("HOP3_ENABLE_AUTH", "true").lower() in {
        "true",
        "1",
        "yes",
    }
    middleware = []

    # Add session middleware (for web UI)
    # Get secret key from environment or generate one (development only)
    session_secret = os.environ.get("HOP3_SESSION_SECRET")
    if not session_secret:
        # In production, this should come from environment
        # For development, generate a random key
        session_secret = secrets.token_urlsafe(32)
        if not DEBUG:
            warnings.warn(
                "HOP3_SESSION_SECRET not set. Using generated key. "
                "Set HOP3_SESSION_SECRET environment variable for production.",
                stacklevel=2,
            )

    middleware.append(
        Middleware(SessionMiddleware, secret_key=session_secret, https_only=not DEBUG)
    )

    if enable_auth:
        # Use composite backend that checks both bearer tokens and sessions
        middleware.append(
            Middleware(
                StarletteAuthMiddleware,
                backend=SessionAuthBackend(),
                on_error=on_auth_error,
            )
        )

    return Starlette(debug=DEBUG, routes=routes, middleware=middleware)
