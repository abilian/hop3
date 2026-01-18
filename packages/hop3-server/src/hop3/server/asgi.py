# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import logging
import os
import secrets
import warnings
from pathlib import Path

from dishka.integrations.litestar import setup_dishka
from litestar import Litestar, Request
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.exceptions import NotAuthorizedException
from litestar.logging import LoggingConfig
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.response import Redirect
from litestar.static_files import create_static_files_router
from litestar.stores.memory import MemoryStore
from litestar.template.config import TemplateConfig
from litestar.types import ControllerRouterHandler

from hop3.di import create_async_container
from hop3.orm import get_session_factory

from .controllers import (
    AuthController,
    DashboardController,
    MarketplaceController,
    RootController,
    RPCController,
)
from .state_sync import start_state_sync_service, stop_state_sync_service

DEBUG = True


class SuppressHTTPExceptionTraceback(logging.Filter):
    """Suppress ERROR-level exception tracebacks for expected HTTP exceptions.

    This filters out tracebacks for 401/404 errors which are normal events,
    while preserving the INFO-level access logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Suppress ERROR logs with HTTP exception tracebacks."""
        if record.levelno != logging.ERROR:
            return True

        # Check if this is an "Uncaught exception" log with traceback
        if "Uncaught exception" not in str(record.msg):
            return True

        # Check exception type in exc_info
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type and exc_type.__name__ in {
                "NotFoundException",
                "NotAuthorizedException",
            }:
                return False

        return True


def handle_401(request: Request, exc: NotAuthorizedException) -> Redirect:
    """Redirect to login page on authentication failure."""
    return Redirect(path="/auth/login")


def on_startup() -> None:
    """Start background services when server starts."""
    session_factory = get_session_factory()
    start_state_sync_service(session_factory)


def on_shutdown() -> None:
    """Stop background services when server shuts down."""
    stop_state_sync_service()


def create_app():
    """Create Litestar application with Dishka DI integration."""
    # Suppress tracebacks for expected HTTP exceptions (401, 404)
    litestar_logger = logging.getLogger("litestar")
    litestar_logger.addFilter(SuppressHTTPExceptionTraceback())

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

    route_handlers: list[ControllerRouterHandler] = [
        RootController,  # Root redirect (/)
        RPCController,  # JSON-RPC endpoint (/rpc)
        AuthController,  # Web authentication (/auth/*)
        DashboardController,  # Dashboard UI (/dashboard/*)
        MarketplaceController,  # Marketplace UI (/dashboard/marketplace/*)
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

    # Configure logging - disable Litestar's request logging since Uvicorn already logs requests
    logging_config = LoggingConfig(
        loggers={
            "litestar": {
                "level": "INFO",
                "handlers": ["console"],
            },
        },
        configure_root_logger=False,  # Don't configure root logger
    )

    # Create app with Litestar session middleware and memory store
    # Allow larger request bodies for deployment packages (default is 10MB)
    # Compiled binaries (Rust, Go) can be 50-100MB+
    # Note: type ignores are for ty's overly strict generic variance checking
    # with Litestar's types (JinjaTemplateEngine is a valid engine, Redirect is a Response)
    app = Litestar(
        route_handlers=route_handlers,
        debug=DEBUG,
        middleware=[session_config.middleware],
        template_config=template_config,
        logging_config=logging_config,
        stores={"sessions": MemoryStore()},
        exception_handlers={
            NotAuthorizedException: handle_401,
        },
        on_startup=[on_startup],
        on_shutdown=[on_shutdown],
        request_max_body_size=200 * 1024 * 1024,  # 200MB for large deployments
    )

    # Setup Dishka dependency injection
    # Litestar integration provides automatic container lifecycle management
    container = create_async_container()
    setup_dishka(container=container, app=app)

    return app


# Create module-level app instance for Litestar CLI
app = create_app()
