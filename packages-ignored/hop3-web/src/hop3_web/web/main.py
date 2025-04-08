# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from pathlib import Path
from typing import Any

import flask_super
import wireup
import wireup.integration.flask
from dotenv import load_dotenv
from flask import Flask
from flask_super.initializers import init_logging
from flask_super.scanner import scan_packages

from hop3_web import services
from hop3_web.web.extensions import init_extensions
from hop3_web.web.setup import register_blueprints

SCANNED_PACKAGES = [
    "hop3_web.orm",
    "hop3_web.web.blueprints",
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

    container = wireup.create_sync_container(
        service_modules=[services],
        parameters={
            **app.config,
            "db_connection_url": app.config["SQLALCHEMY_DATABASE_URI"],
        },
    )

    wireup.integration.flask.setup(container, app)
