# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from dishka.integrations.litestar import setup_dishka
from litestar import Litestar, Request
from litestar.exceptions import NotAuthorizedException
from litestar.logging import LoggingConfig
from litestar.plugins.jinja import JinjaTemplateEngine
from litestar.response import Redirect
from litestar.static_files import create_static_files_router
from litestar.template.config import TemplateConfig

from hop3.config import HOP3_DEBUG
from hop3.core.unsafe_gate import enforce_unsafe_mode_policy
from hop3.di import create_async_container
from hop3.orm import get_session_factory
from hop3.server.security.web_auth import current_identity

from .cert_renewal_service import (
    start_cert_renewal_service,
    stop_cert_renewal_service,
)
from .controllers import (
    AddonsController,
    AppsController,
    AuthController,
    BackupsController,
    CatalogController,
    CertificatesController,
    DashboardIndexController,
    EnvVarsController,
    LogsController,
    RootController,
    RPCController,
    StreamController,
)
from .domain_health_service import (
    start_domain_health_service,
    stop_domain_health_service,
)
from .health import verify_addon_health
from .state_sync import start_state_sync_service, stop_state_sync_service
from .waf_bans_service import start_waf_bans_service, stop_waf_bans_service

if TYPE_CHECKING:
    from litestar.template import TemplateEngineProtocol
    from litestar.types import ControllerRouterHandler

DEBUG = HOP3_DEBUG


class SuppressHTTPExceptionTraceback(logging.Filter):
    """
    Suppress ERROR-level exception tracebacks for expected HTTP exceptions.

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
    # Safety interlock for HOP3_UNSAFE — runs before anything else that
    # could read config.HOP3_UNSAFE. Refuses to boot if the auth bypass
    # was requested without the required ACK flag, and forces it off in
    # production regardless of what the environment asks for.
    enforce_unsafe_mode_policy()

    # Verify addon health (MySQL, PostgreSQL, Redis)
    # Logs warnings if configured services are not accessible
    verify_addon_health()

    session_factory = get_session_factory()
    start_state_sync_service(session_factory)
    # In-process TLS renewal (the primary path; `hop3 cert renew` is a fallback).
    start_cert_renewal_service(session_factory)
    # Domain registration (WHOIS) + DNS health, surfaced on the dashboard.
    start_domain_health_service(session_factory)
    # In-process L7 WAF ban reconciliation (ADR 050 §4); `hop3 waf
    # reconcile-bans` is the manual fallback.
    start_waf_bans_service(session_factory)


def on_shutdown() -> None:
    """Stop background services when server shuts down."""
    stop_state_sync_service()
    stop_cert_renewal_service()
    stop_domain_health_service()
    stop_waf_bans_service()


def _register_template_callables(engine: TemplateEngineProtocol) -> None:
    """
    Expose ``get_current_user()`` to templates.

    Auth is a stateless signed cookie (no server-side session), so templates
    resolve the current user by validating that cookie via ``current_identity``
    rather than reading ``request.session``. Returns the identity dict (with
    ``username``) or None.
    """
    engine.register_template_callable(
        "get_current_user",
        lambda context: current_identity(context["request"]),
    )


def create_app() -> Litestar:
    """Create Litestar application with Dishka DI integration."""
    # Suppress tracebacks for expected HTTP exceptions (401, 404)
    litestar_logger = logging.getLogger("litestar")
    litestar_logger.addFilter(SuppressHTTPExceptionTraceback())

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
        StreamController,  # SSE streaming (/api/stream/*)
        AuthController,  # Web authentication (/auth/*)
        DashboardIndexController,  # Dashboard index (/dashboard/)
        AppsController,  # App management (/dashboard/apps/*)
        LogsController,  # Log viewing (/dashboard/apps/*/logs/*)
        EnvVarsController,  # Environment variables (/dashboard/apps/*/env)
        AddonsController,  # Addon management (/dashboard/addons/*)
        BackupsController,  # Backup management (/dashboard/backups/*)
        CertificatesController,  # TLS cert health (/dashboard/certificates)
        CatalogController,  # Catalog UI (/dashboard/catalog/*)
        static_handler,  # Static files (/static/*)
    ]

    # Authentication is a stateless signed JWT cookie (see security/web_auth.py),
    # so there is no session middleware and no server-side session store — which
    # is exactly why a redeploy no longer logs everyone out.

    # Configure template engine. `get_current_user()` lets templates resolve the
    # logged-in user from the auth cookie (there is no request.session anymore).
    templates_dir = Path(__file__).parent / "templates"
    template_config = TemplateConfig(
        directory=templates_dir,
        engine=JinjaTemplateEngine,
        engine_callback=_register_template_callables,
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

    # Allow larger request bodies for deployment packages (default is 10MB)
    # Compiled binaries (Rust, Go) can be 50-100MB+
    # Note: type ignores are for ty's overly strict generic variance checking
    # with Litestar's types (JinjaTemplateEngine is a valid engine, Redirect is a Response)
    app = Litestar(
        route_handlers=route_handlers,
        debug=DEBUG,
        template_config=template_config,  # type: ignore[arg-type]
        logging_config=logging_config,
        exception_handlers={  # type: ignore[arg-type]
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
