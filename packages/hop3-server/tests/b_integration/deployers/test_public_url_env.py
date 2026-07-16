# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`set_public_url_env` derives HOP3_PUBLIC_URL from the app's HOST_NAME.

This is what lets a recipe reference a single stable ``${HOP3_PUBLIC_URL}``
instead of hand-building the URL. It is a no-op for an app with no real
hostname (empty / the ``_`` catch-all), i.e. one that isn't proxied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.commands._helpers import unset_env_var
from hop3.deployers.env_provisioning import set_env_vars, set_public_url_env
from hop3.orm import App

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _app(session: Session, host_name: str | None = None) -> App:
    app = App(name="wiki")
    session.add(app)
    session.flush()
    if host_name is not None:
        set_env_vars(app, {"HOST_NAME": host_name}, session)
    return app


def test_public_url_set_from_host_name(db_session: Session):
    app = _app(db_session, "wiki.example.com")
    set_public_url_env(app, db_session)
    assert app.get_runtime_env().get("HOP3_PUBLIC_URL") == "https://wiki.example.com"


def test_public_url_uses_first_host(db_session: Session):
    app = _app(db_session, "a.example.com b.example.com")
    set_public_url_env(app, db_session)
    assert app.get_runtime_env().get("HOP3_PUBLIC_URL") == "https://a.example.com"


def test_public_url_noop_without_host_name(db_session: Session):
    app = _app(db_session)
    set_public_url_env(app, db_session)
    assert "HOP3_PUBLIC_URL" not in app.get_runtime_env()


def test_public_url_noop_for_catchall_host(db_session: Session):
    app = _app(db_session, "_")
    set_public_url_env(app, db_session)
    assert "HOP3_PUBLIC_URL" not in app.get_runtime_env()


def test_public_url_first_host_from_comma_form(db_session: Session):
    # HOST_NAME may be stored comma-separated (legacy / user --env); the URL must
    # be the first host, never the whole comma-joined string.
    app = _app(db_session, "a.example.com,b.example.com")
    set_public_url_env(app, db_session)
    assert app.get_runtime_env().get("HOP3_PUBLIC_URL") == "https://a.example.com"


def test_public_url_overwritten_when_host_changes(db_session: Session):
    app = _app(db_session, "old.example.com")
    set_public_url_env(app, db_session)
    assert app.get_runtime_env().get("HOP3_PUBLIC_URL") == "https://old.example.com"

    set_env_vars(app, {"HOST_NAME": "new.example.com"}, db_session)
    set_public_url_env(app, db_session)
    assert app.get_runtime_env().get("HOP3_PUBLIC_URL") == "https://new.example.com"


def test_public_url_cleared_when_host_removed(db_session: Session):
    # Recompute-or-clear: a removed domain must not leave a stale public URL.
    app = _app(db_session, "old.example.com")
    set_public_url_env(app, db_session)
    assert "HOP3_PUBLIC_URL" in app.get_runtime_env()

    unset_env_var(app, "HOST_NAME")
    set_public_url_env(app, db_session)
    assert "HOP3_PUBLIC_URL" not in app.get_runtime_env()
