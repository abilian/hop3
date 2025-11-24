# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import logging
import os
import secrets
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from dishka.integrations.litestar import setup_dishka
from litestar import Litestar, Request, Response
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.exceptions import NotFoundException
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.static_files import create_static_files_router
from litestar.status_codes import HTTP_404_NOT_FOUND
from litestar.stores.memory import MemoryStore
from litestar.template.config import TemplateConfig

from hop3.di import create_async_container

from .controllers import (
    AuthController,
    DashboardController,
    RootController,
    RPCController,
)

if TYPE_CHECKING:
    pass

DEBUG = True


class Suppress404Filter(logging.Filter):
    """Logging filter to suppress 404 exception tracebacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Suppress log records about 404 exceptions."""
        # Suppress ERROR logs about 404/NotFoundException
        if record.levelno == logging.ERROR:
            # Check message content
            msg_str = str(record.msg) if record.msg else ""
            # Check if it's a 404-related log
            if (
                "NotFoundException" in msg_str
                or "404" in msg_str
                or "/nonexistent" in msg_str
                or "/favicon" in msg_str
            ):
                return False
            # Check exception info
            if record.exc_info:
                exc_type = record.exc_info[0]
                if exc_type and exc_type.__name__ == "NotFoundException":
                    return False
        return True


def handle_404(request: Request, exc: NotFoundException) -> Response:
    """Handle 404 errors with minimal logging (no traceback).

    In debug mode, 404s are logged as single-line entries without tracebacks.
    Other exceptions still show full tracebacks in debug mode.
    """
    # Log 404 as INFO level instead of ERROR (no traceback)
    logger = logging.getLogger("litestar")
    logger.info(
        f"[{request.scope.get('method', 'GET')}] {request.url.path} - 404 Not Found"
    )

    return Response(
        content={"detail": "Not Found"},
        status_code=HTTP_404_NOT_FOUND,
    )


def create_app():
    """Create Litestar application with Dishka DI integration.

    All routes are now handled by Litestar controllers.
    Legacy Starlette mount has been removed after complete migration.
    """
    # Configure logging to suppress 404 exception tracebacks
    litestar_logger = logging.getLogger("litestar")
    litestar_logger.addFilter(Suppress404Filter())

    # Get session secret for middleware
    session_secret = os.environ.get("HOP3_SESSION_SECRET")
    if not session_secret:
        session_secret = secrets.token_urlsafe(32)
        if not DEBUG:
            warnings.warn(
                "HOP3_SESSION_SECRET not set. Using generated key. "
                "Set HOP3_SESSION_SECRET environment variable for production.",
                stacklevel=2,
            )

    # Create Litestar app with all controllers
    # Using native Litestar session middleware (Phase 2 migration)

    # Static files router for favicon and other assets
    static_dir = Path(__file__).parent / "static"
    static_handler = create_static_files_router(
        path="/static",
        directories=[static_dir],
    )

    route_handlers = [
        RootController,  # Root redirect (/)
        RPCController,  # JSON-RPC endpoint (/rpc)
        AuthController,  # Web authentication (/auth/*)
        DashboardController,  # Dashboard UI (/dashboard/*)
        static_handler,  # Static files (/static/*)
    ]

    # Configure Litestar server-side session middleware
    # Note: Session data is stored server-side in MemoryStore
    # The secret is not needed since sessions are server-side
    session_config = ServerSideSessionConfig(
        max_age=1209600,  # 14 days in seconds
        httponly=True,
        secure=not DEBUG,  # Only use secure cookies in production
        samesite="lax",
    )

    # Configure template engine
    templates_dir = Path(__file__).parent / "templates"
    template_config = TemplateConfig(
        directory=templates_dir,
        engine=JinjaTemplateEngine,
    )

    # Create app with Litestar session middleware and memory store
    app = Litestar(
        route_handlers=route_handlers,
        debug=DEBUG,
        middleware=[session_config.middleware],
        template_config=template_config,
        stores={"sessions": MemoryStore()},
        exception_handlers={NotFoundException: handle_404},
    )

    # Setup Dishka dependency injection
    # Litestar integration provides automatic container lifecycle management
    container = create_async_container()
    setup_dishka(container=container, app=app)

    return app
