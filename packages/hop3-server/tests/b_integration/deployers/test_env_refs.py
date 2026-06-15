# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dynamic [env] references resolve against addon and app facts (ADR 046 §1b).

`{ from = "<addon>", key = "<KEY>" }` copies an attribute from a declared
addon's stored credentials; `{ key = "domain"/"name" }` reads an app fact. An
unresolvable reference must abort loudly, never produce a wrong value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.core.credentials import get_credential_encryptor
from hop3.deployers.env_provisioning import resolve_env_refs, set_env_vars
from hop3.orm import AddonCredential, App

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _app(session: Session, name: str = "refs-app") -> App:
    app = App(name=name)
    session.add(app)
    session.flush()
    return app


def _attach(session: Session, app: App, addon_name: str, details: dict) -> None:
    session.add(
        AddonCredential(
            app_id=app.id,
            addon_type="postgres",
            addon_name=addon_name,
            encrypted_data=get_credential_encryptor().encrypt(details),
        )
    )
    session.flush()


def test_resolves_addon_ref(db_session: Session):
    app = _app(db_session)
    url = "postgresql://u:p@127.0.0.1:5432/db"
    _attach(
        db_session, app, "refs-app-db", {"DATABASE_URL": url, "PGHOST": "127.0.0.1"}
    )

    resolve_env_refs(
        app, {"MY_DB": {"from": "refs-app-db", "key": "DATABASE_URL"}}, db_session
    )
    assert app.get_runtime_env().get("MY_DB") == url


def test_resolves_app_domain_fact(db_session: Session):
    app = _app(db_session)
    set_env_vars(
        app, {"HOST_NAME": "refs-app.example.com other.example.com"}, db_session
    )

    resolve_env_refs(app, {"FQDN": {"key": "domain"}}, db_session)
    assert app.get_runtime_env().get("FQDN") == "refs-app.example.com"  # first host


def test_resolves_app_name_fact(db_session: Session):
    app = _app(db_session)
    resolve_env_refs(app, {"WHO": {"key": "name"}}, db_session)
    assert app.get_runtime_env().get("WHO") == "refs-app"


def test_unattached_addon_fails_loud(db_session: Session):
    app = _app(db_session)
    with pytest.raises(ValueError, match="not attached"):
        resolve_env_refs(
            app, {"X": {"from": "nope", "key": "DATABASE_URL"}}, db_session
        )


def test_unknown_addon_key_fails_loud(db_session: Session):
    app = _app(db_session)
    _attach(db_session, app, "refs-app-db", {"DATABASE_URL": "x"})
    with pytest.raises(ValueError, match="no key 'MISSING'"):
        resolve_env_refs(
            app, {"X": {"from": "refs-app-db", "key": "MISSING"}}, db_session
        )


def test_domain_fact_without_hostname_fails_loud(db_session: Session):
    app = _app(db_session)
    with pytest.raises(ValueError, match="no hostname"):
        resolve_env_refs(app, {"FQDN": {"key": "domain"}}, db_session)


def test_external_ip_not_implemented(db_session: Session):
    app = _app(db_session)
    with pytest.raises(ValueError, match="external_ip"):
        resolve_env_refs(app, {"IP": {"external_ip": True}}, db_session)


def test_empty_config_is_a_noop(db_session: Session):
    app = _app(db_session)
    resolve_env_refs(app, {}, db_session)
    assert app.env_vars == []
