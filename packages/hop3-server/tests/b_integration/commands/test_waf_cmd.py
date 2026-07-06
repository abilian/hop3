# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 waf bans` — operator view + control of L7 ban runtime state (ADR 050 §9)."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING

from hop3.commands import waf as waf_cmd
from hop3.commands.waf import (
    WafBansClearCmd,
    WafBansListCmd,
    WafLogsCmd,
    WafStatusCmd,
)
from hop3.orm import App, Ban, BanRepository
from hop3.plugins.waf.lewaf.engine import LeWafEngine
from hop3.waf.bans import utcnow

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _app(db_session: Session, name: str = "myapp") -> App:
    app = App(name=name)
    db_session.add(app)
    db_session.flush()
    return app


def _ban(db_session: Session, app: App, source: str) -> None:
    db_session.add(
        Ban(
            app_id=app.id,
            app_name=app.name,
            source=source,
            reason="5 violations in 10m",
            expires_at=utcnow() + timedelta(hours=1),
        )
    )
    db_session.flush()


def test_bans_list_empty(db_session: Session):
    out = WafBansListCmd(db_session=db_session).call()
    assert out[0]["t"] == "text"
    assert "No active WAF bans" in out[0]["text"]


def test_bans_list_shows_active(db_session: Session):
    app = _app(db_session)
    _ban(db_session, app, "198.51.100.9")
    out = WafBansListCmd(db_session=db_session).call()
    assert out[0]["t"] == "table"
    assert out[0]["rows"][0][0] == "myapp"
    assert out[0]["rows"][0][1] == "198.51.100.9"


def test_bans_list_filters_by_app(db_session: Session):
    a = _app(db_session, "a")
    b = _app(db_session, "b")
    _ban(db_session, a, "1.1.1.1")
    _ban(db_session, b, "2.2.2.2")
    out = WafBansListCmd(db_session=db_session).call("a")
    assert {r[1] for r in out[0]["rows"]} == {"1.1.1.1"}


def test_bans_clear_removes_and_rewrites_denylist(db_session, tmp_path, monkeypatch):
    engine = LeWafEngine(rules_dir=tmp_path, log_dir=tmp_path)
    monkeypatch.setattr(waf_cmd, "get_waf_engine", lambda name="lewaf": engine)
    app = _app(db_session)
    _ban(db_session, app, "198.51.100.9")

    out = WafBansClearCmd(db_session=db_session).call("myapp")

    assert "Cleared 1 ban" in out[0]["text"]
    assert BanRepository(session=db_session).list_active(app.id, utcnow()) == []
    # the denylist file was regenerated without the lifted source
    assert "198.51.100.9" not in engine._bans_path("myapp").read_text()


def test_bans_clear_unknown_app_errors(db_session: Session):
    out = WafBansClearCmd(db_session=db_session).call("ghost")
    assert out[0]["t"] == "error"


def test_status_empty(db_session: Session):
    out = WafStatusCmd(db_session=db_session).call()
    assert out[0]["t"] == "text"
    assert "No apps have the WAF enabled" in out[0]["text"]


def test_status_lists_waf_apps(db_session: Session):
    app = _app(db_session)
    app.waf_port = 9123
    db_session.flush()
    _ban(db_session, app, "198.51.100.9")
    out = WafStatusCmd(db_session=db_session).call()
    assert out[0]["t"] == "table"
    row = out[0]["rows"][0]
    assert row[0] == "myapp"
    assert row[1] == "9123"
    assert row[3] == "1"  # one active ban


def test_logs_shows_audit_entries(db_session, tmp_path, monkeypatch):
    engine = LeWafEngine(rules_dir=tmp_path, log_dir=tmp_path)
    monkeypatch.setattr(waf_cmd, "get_waf_engine", lambda name="lewaf": engine)
    app = _app(db_session)
    app.waf_port = 9123
    db_session.flush()
    audit = engine.audit_path("myapp")
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(
        json.dumps({
            "timestamp": "2026-06-25T12:00:00",
            "client_ip": "198.51.100.9",
            "action": "blocked",
            "rule_id": 942100,
            "request_uri": "/wp-admin",
        })
        + "\n"
    )
    out = WafLogsCmd(db_session=db_session).call()
    assert out[0]["t"] == "table"
    assert out[0]["rows"][0][2] == "198.51.100.9"
    assert out[0]["rows"][0][3] == "blocked"
