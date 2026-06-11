# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""ASGI application factory (mirrors ``hop3.server.asgi.create_app``).

Granian boots this factory (``hop3_testlab.web.asgi:create_app``, ``factory=True``).
Dishka is attached after construction via ``setup_dishka`` (same as hop3-server).
"""

from __future__ import annotations

from pathlib import Path

from dishka.integrations.litestar import setup_dishka
from litestar import Litestar
from litestar.config.csrf import CSRFConfig
from litestar.exceptions import NotAuthorizedException
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.plugins.jinja import JinjaTemplateEngine
from litestar.response import Redirect
from litestar.stores.memory import MemoryStore
from litestar.template.config import TemplateConfig

from hop3_testlab.cloud_config import load_schedule
from hop3_testlab.config import TestlabConfig
from hop3_testlab.di import create_async_container
from hop3_testlab.scheduler import build_background_scheduler
from hop3_testlab.web.controllers import (
    AuthController,
    BuildController,
    BundleController,
    DashboardController,
    HealthController,
    ProfilesController,
    RunningController,
    RunsController,
    TrendsController,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _handle_unauthorized(_request, _exc) -> Redirect:
    """Browser-friendly: send unauthenticated requests to the login page."""
    return Redirect(path="/auth/login")


def _on_startup(app: Litestar) -> None:
    """Start the in-process nightly scheduler when [schedule].enabled."""
    if not load_schedule().enabled:
        return
    scheduler = build_background_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler


def _on_shutdown(app: Litestar) -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def create_app() -> Litestar:
    """Build the Test Lab Litestar application."""
    config = TestlabConfig.get_instance()
    session_config = ServerSideSessionConfig()
    # CSRF-protect the state-changing POSTs (stop / trigger / login). Disabled
    # under the same UNSAFE flag that bypasses auth (tests/dev), so the test
    # client doesn't have to round-trip a token. SameSite=Lax (the cookie
    # default) already blunts cross-site POSTs; this is defence in depth for when
    # the dashboard gains broader exposure.
    csrf_config = None if config.UNSAFE else CSRFConfig(secret=config.SECRET_KEY)
    app = Litestar(
        route_handlers=[
            HealthController,
            AuthController,
            DashboardController,
            RunningController,
            RunsController,
            BundleController,
            BuildController,
            TrendsController,
            ProfilesController,
        ],
        template_config=TemplateConfig(
            directory=TEMPLATES_DIR, engine=JinjaTemplateEngine
        ),
        middleware=[session_config.middleware],
        csrf_config=csrf_config,
        stores={"sessions": MemoryStore()},
        exception_handlers={NotAuthorizedException: _handle_unauthorized},
        on_startup=[_on_startup],
        on_shutdown=[_on_shutdown],
        debug=config.DEBUG,
    )
    setup_dishka(container=create_async_container(), app=app)
    return app


# Module-level app for the Litestar CLI / ASGI servers that import an `app`.
app = create_app()
