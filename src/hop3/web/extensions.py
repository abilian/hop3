# Copyright (c) 2019-2024, Abilian SAS - All rights reserved

from __future__ import annotations

from blinker import ANY
from devtools import debug
from flask import Flask
from flask_babel import Babel
from flask_htmx import HTMX
from flask_mail import Mail, email_dispatched
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.query import Query
from flask_talisman import DEFAULT_CSP_POLICY, Talisman
from flask_vite import Vite
from pytz import timezone

try:
    from flask_debugtoolbar import DebugToolbarExtension
except ImportError:
    DebugToolbarExtension = None

from hop3.model.security import User

PARIS_TZ = timezone("Europe/Paris")

db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
htmx = HTMX()
vite = Vite()

babel = Babel(default_locale="fr_FR", default_timezone=PARIS_TZ)


def init_extensions(app: Flask) -> None:
    db.init_app(app)
    mail.init_app(app)
    babel.init_app(app)
    migrate.init_app(app, db)
    htmx.init_app(app)
    vite.init_app(app)

    if app.debug and DebugToolbarExtension:
        DebugToolbarExtension(app)

    if not app.debug:
        csp = app.config.get("CONTENT_SECURITY_POLICY", DEFAULT_CSP_POLICY)
        Talisman(app, content_security_policy=csp)


@email_dispatched.connect_via(ANY)
def debug_email(app, message):
    if not app.debug:
        return

    debug(vars(message))


# HACK
# (Avoids writing our own SQLAlchemyUserDatastore-like class)
class QueryProperty:
    # Adapted from flask-sqlalchemy (flask_sqlalchemy/model.py)

    def __get__(self, obj, cls) -> Query:
        return Query(cls, session=db.session())


# Monkey-patch to make it quack like a db.Model
User.query = QueryProperty()
