# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Attached addons are re-injected into the runtime env on every deploy.

Regression for the demo10 failure: an addon attached manually (``hop3 addon
attach``, no ``[[addons]]`` in hop3.toml) was never re-derived at deploy, so its
``DATABASE_URL`` could go missing on redeploy. The runtime env must instead be a
function of the stored ``AddonCredential`` rows (the source of truth).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.core.credentials import get_credential_encryptor
from hop3.deployers.addon_provisioning import reinject_attached_addons
from hop3.orm import AddonCredential, App

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _app(session: Session, name: str = "demo10") -> App:
    app = App(name=name)
    session.add(app)
    session.flush()
    return app


def _attach(session: Session, app: App, name: str, details: dict) -> None:
    session.add(
        AddonCredential(
            app_id=app.id,
            addon_type="postgres",
            addon_name=name,
            encrypted_data=get_credential_encryptor().encrypt(details),
        )
    )
    session.flush()


def test_attached_addon_is_reinjected_into_runtime_env(db_session: Session):
    app = _app(db_session)
    url = "postgresql://demo10_db_user:secret@127.0.0.1:5432/demo10_db"
    _attach(db_session, app, "demo10-db", {"DATABASE_URL": url, "PGHOST": "127.0.0.1"})

    # Manually-attached addon: nothing in the runtime env yet (the bug).
    assert app.get_runtime_env().get("DATABASE_URL") is None

    reinject_attached_addons(app, db_session)  # what every deploy now does

    env = app.get_runtime_env()
    assert env.get("DATABASE_URL") == url
    assert env.get("PGHOST") == "127.0.0.1"


def test_reinjection_recovers_after_env_churn(db_session: Session):
    app = _app(db_session)
    url = "postgresql://u:p@127.0.0.1:5432/db"
    _attach(db_session, app, "db", {"DATABASE_URL": url})

    reinject_attached_addons(app, db_session)
    assert app.get_runtime_env().get("DATABASE_URL") == url

    # Whatever clears env_vars, the credential remains the source of truth.
    app.env_vars.clear()
    db_session.flush()
    assert app.get_runtime_env().get("DATABASE_URL") is None

    reinject_attached_addons(app, db_session)  # next deploy re-derives it
    assert app.get_runtime_env().get("DATABASE_URL") == url


def test_no_attached_addons_is_a_noop(db_session: Session):
    app = _app(db_session, "plain")
    reinject_attached_addons(app, db_session)  # must not raise
    assert app.get_runtime_env().get("DATABASE_URL") is None
