# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Generated secrets are materialized once and never rotate (ADR 046).

`set_generated_env_vars` creates a secret only when the var is unset, persists
it as a normal env var, and leaves it untouched on every later deploy — so a
release that hard-requires SECRET_KEY_BASE at boot gets a stable value and a
redeploy never invalidates sessions by silently rotating the secret.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.deployers.env_provisioning import set_env_vars, set_generated_env_vars
from hop3.orm import App

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _app(session: Session, name: str = "phoenix") -> App:
    app = App(name=name)
    session.add(app)
    session.flush()
    return app


def test_generates_when_unset(db_session: Session):
    app = _app(db_session)
    set_generated_env_vars(
        app, {"SECRET_KEY_BASE": {"generate": "hex", "length": 64}}, db_session
    )
    assert len(app.get_runtime_env().get("SECRET_KEY_BASE")) == 128  # 64 bytes hex


def test_generated_once_does_not_rotate(db_session: Session):
    app = _app(db_session)
    spec = {"SECRET_KEY_BASE": {"generate": "hex"}}

    set_generated_env_vars(app, spec, db_session)
    first = app.get_runtime_env().get("SECRET_KEY_BASE")

    set_generated_env_vars(app, spec, db_session)  # a later redeploy
    assert app.get_runtime_env().get("SECRET_KEY_BASE") == first


def test_respects_a_preexisting_value(db_session: Session):
    app = _app(db_session)
    set_env_vars(app, {"APP_KEY": "set-by-user"}, db_session)

    set_generated_env_vars(app, {"APP_KEY": {"generate": "base64"}}, db_session)
    assert app.get_runtime_env().get("APP_KEY") == "set-by-user"


def test_prefix_is_applied(db_session: Session):
    app = _app(db_session)
    set_generated_env_vars(
        app, {"APP_KEY": {"generate": "base64", "prefix": "base64:"}}, db_session
    )
    assert app.get_runtime_env().get("APP_KEY").startswith("base64:")


def test_empty_config_is_a_noop(db_session: Session):
    app = _app(db_session)
    set_generated_env_vars(app, {}, db_session)  # must not raise
    assert app.env_vars == []
