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

import pytest

from hop3.core.credentials import get_credential_encryptor
from hop3.deployers.addon_provisioning import addon_var_names, sync_addon_env_vars
from hop3.lib import Abort
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

    sync_addon_env_vars(app, db_session)  # what every deploy now does

    env = app.get_runtime_env()
    assert env.get("DATABASE_URL") == url
    assert env.get("PGHOST") == "127.0.0.1"


def test_reinjection_recovers_after_env_churn(db_session: Session):
    app = _app(db_session)
    url = "postgresql://u:p@127.0.0.1:5432/db"
    _attach(db_session, app, "db", {"DATABASE_URL": url})

    sync_addon_env_vars(app, db_session)
    assert app.get_runtime_env().get("DATABASE_URL") == url

    # Whatever clears env_vars, the credential remains the source of truth.
    app.env_vars.clear()
    db_session.flush()
    assert app.get_runtime_env().get("DATABASE_URL") is None

    sync_addon_env_vars(app, db_session)  # next deploy re-derives it
    assert app.get_runtime_env().get("DATABASE_URL") == url


def test_no_attached_addons_is_a_noop(db_session: Session):
    app = _app(db_session, "plain")
    sync_addon_env_vars(app, db_session)  # must not raise
    assert app.get_runtime_env().get("DATABASE_URL") is None


def _corrupt(session: Session, app: App, name: str) -> None:
    session.add(
        AddonCredential(
            app_id=app.id,
            addon_type="postgres",
            addon_name=name,
            encrypted_data="not-a-fernet-token",
        )
    )
    session.flush()


def test_an_unreadable_credential_stops_the_deploy(db_session: Session):
    """Skipping it deployed the app with no DATABASE_URL, failing far away."""
    app = _app(db_session)
    _corrupt(db_session, app, "demo10-db")

    with pytest.raises(Abort, match=r"addon 'demo10-db'.*cannot be decrypted"):
        sync_addon_env_vars(app, db_session)


def test_an_unreadable_credential_is_not_labelled_user_set(db_session: Session):
    app = _app(db_session)
    _corrupt(db_session, app, "demo10-db")

    with pytest.raises(Abort, match="hop3 addon attach demo10-db --app demo10"):
        addon_var_names(app, db_session)
