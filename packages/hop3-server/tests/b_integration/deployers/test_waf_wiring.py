# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Deploy-time WAF wiring helpers (ADR 050).

The full preflight -> proxy -> teardown path runs in the Docker e2e layer; here
we pin the engine-independent data transforms: turning the raw ``[waf]`` table
into a validated policy, and resolving operator named networks from the DB.
"""

from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

from hop3.deployers import waf as waf_mod
from hop3.deployers.waf import (
    _daemon_command,
    _resolve_networks,
    _waf_section,
    reconcile_bans,
)
from hop3.orm import App, BanRepository, Network
from hop3.plugins.waf.lewaf.engine import LeWafEngine
from hop3.waf.bans import utcnow


def _config(waf: dict):
    """A stand-in AppConfig exposing only ``.hop3_config.waf``."""
    return SimpleNamespace(hop3_config=SimpleNamespace(waf=waf))


def test_waf_section_is_none_when_absent():
    assert _waf_section(_config({})) is None


def test_waf_section_validates_the_policy():
    section = _waf_section(_config({"enabled": True, "allow": ["/", "/api/.*"]}))
    assert section is not None
    assert section.enabled
    assert section.allow == ["/", "/api/.*"]


def test_resolve_networks_without_session_is_empty():
    assert _resolve_networks(None) == {}


def test_resolve_networks_maps_name_to_cidrs(db_session):
    db_session.add(Network(name="office", cidrs=["203.0.113.0/24", "10.0.0.0/8"]))
    db_session.add(Network(name="vpn", cidrs=["10.8.0.0/24"]))
    db_session.flush()

    assert _resolve_networks(db_session) == {
        "office": ["203.0.113.0/24", "10.0.0.0/8"],
        "vpn": ["10.8.0.0/24"],
    }


def test_daemon_command_execs_and_redirects_to_log():
    cmd = [
        "/venv/bin/python",
        "-m",
        "hop3.plugins.waf.lewaf._proxy_main",
        "--port",
        "9000",
    ]
    daemon = _daemon_command(cmd, "/home/hop3/apps/x/log/waf.1.log")
    # exec (clean reaping) + both streams appended to the app log (never /dev/null)
    assert daemon.startswith('sh -c "exec ')
    assert "hop3.plugins.waf.lewaf._proxy_main" in daemon
    assert ">>/home/hop3/apps/x/log/waf.1.log 2>&1" in daemon


# --- ban scorer reconciliation (ADR 050 §4) -------------------------------


def _bans_config(**bans):
    waf = {"enabled": True, "allow": ["/"], "bans": {"enabled": True, **bans}}
    return SimpleNamespace(hop3_config=SimpleNamespace(waf=waf))


def _tmp_engine(tmp_path, monkeypatch) -> LeWafEngine:
    """Inject a tmp-dir engine so reconcile_bans stays hermetic."""
    engine = LeWafEngine(rules_dir=tmp_path, log_dir=tmp_path)
    monkeypatch.setattr(waf_mod, "get_waf_engine", lambda name="lewaf": engine)
    return engine


def _write_audit(engine, app_name, ip, count, now):
    audit = engine.audit_path(app_name)
    audit.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({
            "action": "blocked",
            "client_ip": ip,
            "timestamp": (now - timedelta(minutes=i)).isoformat(),
        })
        for i in range(count)
    ]
    audit.write_text("\n".join(lines) + "\n")


def _app(db_session, name="myapp") -> App:
    app = App(name=name)
    db_session.add(app)
    db_session.flush()
    return app


def test_reconcile_bans_bans_repeat_offender(db_session, tmp_path, monkeypatch):
    engine = _tmp_engine(tmp_path, monkeypatch)
    app = _app(db_session)
    now = utcnow()
    _write_audit(engine, app.name, "198.51.100.9", count=6, now=now)

    active = reconcile_bans(
        app, _bans_config(threshold=5, window="10m", duration="1h"), db_session, now=now
    )

    assert active == 1
    bans = BanRepository(session=db_session).list_active(app.id, now)
    assert [b.source for b in bans] == ["198.51.100.9"]
    # the banned IP is written into the engine's denylist file
    assert "198.51.100.9" in engine._bans_path(app.name).read_text()


def test_reconcile_bans_spares_sources_under_threshold(
    db_session, tmp_path, monkeypatch
):
    engine = _tmp_engine(tmp_path, monkeypatch)
    app = _app(db_session)
    now = utcnow()
    _write_audit(engine, app.name, "198.51.100.9", count=3, now=now)

    active = reconcile_bans(
        app, _bans_config(threshold=5, window="10m", duration="1h"), db_session, now=now
    )
    assert active == 0


def test_reconcile_bans_exempts_named_networks(db_session, tmp_path, monkeypatch):
    """Security invariant 5: a source in a named network is never banned."""
    engine = _tmp_engine(tmp_path, monkeypatch)
    db_session.add(Network(name="office", cidrs=["198.51.100.0/24"]))
    app = _app(db_session)
    now = utcnow()
    _write_audit(engine, app.name, "198.51.100.9", count=10, now=now)

    active = reconcile_bans(
        app, _bans_config(threshold=5, window="10m", duration="1h"), db_session, now=now
    )
    assert active == 0


def test_reconcile_bans_expires_elapsed_bans(db_session, tmp_path, monkeypatch):
    engine = _tmp_engine(tmp_path, monkeypatch)
    app = _app(db_session)
    now = utcnow()
    _write_audit(engine, app.name, "198.51.100.9", count=6, now=now)
    reconcile_bans(
        app, _bans_config(threshold=5, window="10m", duration="1h"), db_session, now=now
    )

    # No fresh violations, and the clock has moved past the ban TTL.
    engine.audit_path(app.name).write_text("")
    later = now + timedelta(hours=2)
    active = reconcile_bans(
        app,
        _bans_config(threshold=5, window="10m", duration="1h"),
        db_session,
        now=later,
    )
    assert active == 0
    assert "198.51.100.9" not in engine._bans_path(app.name).read_text()
