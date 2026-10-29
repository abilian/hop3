# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import anyio.to_thread
from dishka.integrations.litestar import setup_dishka
from litestar import Litestar, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.logging import LoggingConfig
from litestar.plugins.jinja import JinjaTemplateEngine
from litestar.response import Redirect, Response, Template
from litestar.static_files import create_static_files_router
from litestar.template.config import TemplateConfig

from hop3 import config as c
from hop3.core.unsafe_gate import enforce_unsafe_mode_policy
from hop3.di import create_async_container
from hop3.di.providers import current_request_session, roll_back_if_uncommitted
from hop3.lib.logging import server_log
from hop3.orm import get_session_factory
from hop3.server.security.web_auth import current_identity

from .cert_renewal_service import (
    start_cert_renewal_service,
    stop_cert_renewal_service,
)
from .controllers import (
    AccessGateController,
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
    from litestar.types import ControllerRouterHandler, Scope


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
                "PermissionDeniedException",
            }:
                return False

        return True


LOGIN_PATH = "/auth/login"


UNSAVED_CHANGE_MESSAGE = (
    "The change was not saved: the server answered before committing it, and "
    "rolled it back. This is a Hop3 bug; the server log names the page."
)


async def refuse_uncommitted_writes(response: Response) -> Response:
    """
    Answer an error, not the handler's success, when it left writes uncommitted.

    The request scope closes after the response is sent, so its own check can
    only reach the log: the browser would have been told the change worked.
    This runs before the response goes out and replaces it.
    """
    session = current_request_session()
    if session is None:
        return response
    if not await anyio.to_thread.run_sync(roll_back_if_uncommitted, session):
        return response
    server_log.error(
        "A handler answered without committing its database writes; "
        "they were rolled back and the response replaced with an error",
    )
    return Response(
        content=UNSAVED_CHANGE_MESSAGE, status_code=500, media_type="text/plain"
    )


async def roll_back_on_exception(_exc: Exception, _scope: Scope) -> None:
    """
    Roll back the request's session when its handler raised.

    Litestar turns the exception into a response before the request scope
    closes, so the scope never learns the handler failed: its writes would
    still be pending there and be reported as a forgotten commit.
    """
    session = current_request_session()
    if session is not None:
        await anyio.to_thread.run_sync(session.rollback)


def handle_401(request: Request, exc: NotAuthorizedException) -> Redirect | Response:
    """
    Send an unauthenticated caller to sign in, in the form it can act on.

    ``/api/`` clients (the CLI streaming a deploy) get JSON with the status,
    as `handle_403` gives them; a redirect to an HTML page is a body they
    cannot parse. An HTMX request gets ``HX-Redirect``: a plain redirect would
    be followed by the XHR and the login page swapped into the fragment.
    """
    if request.url.path.startswith("/api/"):
        return Response(
            content={"status_code": 401, "detail": exc.detail},
            status_code=401,
        )
    if request.headers.get("HX-Request") == "true":
        return Response(
            content=b"", status_code=401, headers={"HX-Redirect": LOGIN_PATH}
        )
    return Redirect(path=LOGIN_PATH)


def handle_403(request: Request, exc: PermissionDeniedException) -> Template | Response:
    """
    Say which role a page needs (ADR 061 §4), as a page or, for the API, JSON.

    ``/api/`` clients (the CLI streaming a deploy) read the status and detail;
    a browser gets a page naming the role and the admin command that grants it.
    """
    if request.url.path.startswith("/api/"):
        return Response(
            content={"status_code": 403, "detail": exc.detail},
            status_code=403,
        )
    return Template(
        template_name="auth/forbidden.html",
        context={"detail": exc.detail},
        status_code=403,
    )


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
        AccessGateController,  # Access gate (/auth/check, /_hop3/auth/*)
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
        debug=c.HOP3_DEBUG,
        template_config=template_config,  # type: ignore[arg-type]
        logging_config=logging_config,
        exception_handlers={  # type: ignore[arg-type]
            NotAuthorizedException: handle_401,
            PermissionDeniedException: handle_403,
        },
        on_startup=[on_startup],
        on_shutdown=[on_shutdown],
        after_request=refuse_uncommitted_writes,
        after_exception=[roll_back_on_exception],
        request_max_body_size=200 * 1024 * 1024,  # 200MB for large deployments
    )

    # Setup Dishka dependency injection
    # Litestar integration provides automatic container lifecycle management
    container = create_async_container()
    setup_dishka(container=container, app=app)

    return app
