# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
An open log stream must not hold a database connection.

The request scope, and its session, lasts until the response is sent: for the
live log stream, until the tab is closed. The lookup left its read transaction
open, so each open tab kept a pooled connection, and fifteen tabs blocked
every other request.
"""

from __future__ import annotations

from hop3.orm import App, AppRepository
from hop3.server.controllers.dashboard.logs import _find_log_dir


def test_the_lookup_hands_the_connection_back(db_session):
    db_session.add(App(name="myapp"))
    db_session.commit()

    log_dir = _find_log_dir(AppRepository(session=db_session), "myapp")

    assert log_dir is not None
    assert log_dir.name == "log"
    assert not db_session.in_transaction()


def test_a_missing_app_is_none(db_session):
    assert _find_log_dir(AppRepository(session=db_session), "nope") is None
    assert not db_session.in_transaction()
