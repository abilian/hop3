# Copyright (c) 2019-2024, Abilian SAS - All rights reserved
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import os

from flask import Flask, g, render_template_string
from flask_login import current_user
from flask_security import Security, SQLAlchemyUserDatastore, auth_required
from hop3_web.web.extensions import db

CONFIG = {
    "SECRET_KEY": os.environ.get("SECRET_KEY", "xxx"),
    "SECURITY_PASSWORD_SALT": os.environ.get("SECURITY_PASSWORD_SALT", "xxx"),
    "SECURITY_REGISTERABLE": True,
    "SECURITY_CONFIRMABLE": True,
    "SECURITY_RECOVERABLE": True,
    "SECURITY_CHANGEABLE": True,
    "REMEMBER_COOKIE_SAMESITE": "strict",
    "SESSION_COOKIE_SAMESITE": "strict",
    "SECURITY_TRACKABLE": True,
}

security = Security()


def init_app(app: Flask) -> None:
    from hop3_web.models.auth import Role, User

    app.config.update(CONFIG)
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)

    security.init_app(app, user_datastore, datetime_factory=utcnow)

    # Views
    @app.route("/test-auth/")
    @auth_required()
    def home():
        return render_template_string("Hello {{ current_user.email }}")

    @app.before_request
    def before_request():
        g.current_user = current_user
