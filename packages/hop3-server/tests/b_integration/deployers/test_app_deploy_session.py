# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
``App.deploy()`` deploys in the app's own session.

Backup restore calls ``app.deploy()``. It used to reach ``do_deploy`` with no
session, and the deploy then skipped addon provisioning, the admin account and
the smoke test without a word.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3 import deployers
from hop3.lib import Abort
from hop3.orm import App

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_deploy_hands_over_the_session_the_app_lives_in(
    db_session: Session, monkeypatch
):
    app = App(name="restored")
    db_session.add(app)
    db_session.flush()
    received = []
    monkeypatch.setattr(
        deployers, "do_deploy", lambda a, *, db_session: received.append(db_session)
    )

    app.deploy()

    assert received == [db_session]


def test_a_detached_app_refuses_to_deploy(monkeypatch):
    monkeypatch.setattr(deployers, "do_deploy", lambda *_a, **_k: pytest.fail("ran"))

    with pytest.raises(Abort, match="not attached to a database session"):
        App(name="orphan").deploy()
