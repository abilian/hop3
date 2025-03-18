# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from pathlib import Path
from typing import Any

import flask_super
from dotenv import load_dotenv
from flask import Flask
from flask_super.initializers import init_logging
from flask_super.scanner import scan_packages

from hop3_web.web.extensions import init_extensions
from hop3_web.web.setup import register_blueprints

# from app.cli import register_commands
# from app.config import finish_config
# from app.extensions import init_extensions
# from app.lib.macros import register_macros
# from app.lib.routes import register_blueprints
# from app.security import init_app as init_security
# from app.services import register_services
# from app.setup.errors import init_error_handlers
# from app.setup.hooks import register_hooks
# from app.setup.sentry import init_sentry

# from .security import ExtendedConfirmRegisterForm, user_datastore

SCANNED_PACKAGES = [
    "hop3_main.models",
    "hop3_main.web.blueprints",
    # "app.components",
    # "app.cli",
    # "app.services.blobs",
]


def create_app(config: Any = None) -> Flask:
    # When testing
    if config:
        app = Flask(__name__)
        app.config.from_object(config)

    # Otherwise
    else:
        # Not needed when called from CLI, but needed when
        # called from a WSGI server
        load_dotenv(verbose=True)

        root = Path().absolute()
        app = Flask(__name__, instance_path=str(root / "instance"))
        app.config.from_prefixed_env()

        # finish_config(app)

    init_app(app)
    return app


def init_app(app: Flask) -> None:
    # Logging & Observability
    init_logging(app)
    # init_sentry(app)

    # Scan modules that may provide side effects
    scan_packages(SCANNED_PACKAGES)

    # Services / Extensions
    init_extensions(app)
    # init_security(app)
    # register_services(app)

    # CLI
    # register_commands(app)

    # Flask-Super
    flask_super.init_app(app)

    # FIXME
    # configure_csp(app)

    # Web
    # init_error_handlers(app)
    register_blueprints(app)

    # Context processors
    # register_hooks(app)

    # Macros (Jinja)
    # register_macros(app)
