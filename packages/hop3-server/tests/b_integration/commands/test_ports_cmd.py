# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 ports` (port list) — read-only view of the fixed-port registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.commands.ports import PortsCmd
from hop3.orm import App, PortClaim

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _app(session: Session, name: str) -> App:
    app = App(name=name)
    session.add(app)
    session.flush()
    return app


def test_empty_registry_reports_no_ports(db_session: Session):
    out = PortsCmd(db_session=db_session).call()
    assert out[0]["t"] == "text"
    assert "No fixed host ports" in out[0]["text"]


def test_lists_claims_with_source_and_firewall_status(db_session: Session):
    app = _app(db_session, "owncast-1")
    # One opened (rule_id set), one merely claimed (rule_id None, e.g. Docker).
    db_session.add(
        PortClaim(
            app_id=app.id,
            number=1935,
            protocol="tcp",
            app_name="owncast-1",
            source="any",
            rule_id="rule-1",
        )
    )
    db_session.add(
        PortClaim(
            app_id=app.id,
            number=5432,
            protocol="tcp",
            app_name="owncast-1",
            source="10.0.0.0/8",
            rule_id=None,
        )
    )
    db_session.flush()

    out = PortsCmd(db_session=db_session).call()
    assert out[0]["t"] == "table"
    assert out[0]["headers"] == ["Port", "Proto", "App", "Source", "Firewall"]
    rows = out[0]["rows"]
    # Sorted by (number, protocol): 1935 then 5432.
    assert rows[0] == [1935, "tcp", "owncast-1", "any", "open"]
    assert rows[1] == [5432, "tcp", "owncast-1", "10.0.0.0/8", "claimed"]


def test_rejects_stray_args(db_session: Session):
    with pytest.raises(ValueError, match="takes no arguments"):
        PortsCmd(db_session=db_session).call("extra")
