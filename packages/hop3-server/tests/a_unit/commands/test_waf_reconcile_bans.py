# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
`hop3 waf reconcile-bans` names the apps it could not score.

It used to `continue` past any app whose config failed to load and still
report a total, so a WAF-enabled app went unbanned with nothing said.
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3.commands import waf as waf_cmd
from hop3.commands.waf import WafReconcileBansCmd
from hop3.orm import App
from hop3.project.config import AppConfig


def test_reports_waf_apps_whose_config_failed_to_load(db_session, monkeypatch):
    db_session.add_all([
        App(name="good", waf_port=4001),
        App(name="broken", waf_port=4002),
        App(name="nowaf"),  # never loaded: it has no WAF to score
    ])
    db_session.commit()
    loaded: list[str] = []

    def from_dir(path):
        loaded.append(path.name)
        if path.name == "broken":
            msg = "hop3.toml: invalid TOML at line 3"
            raise ValueError(msg)
        return SimpleNamespace()

    monkeypatch.setattr(AppConfig, "from_dir", staticmethod(from_dir))
    monkeypatch.setattr(waf_cmd, "reconcile_bans", lambda app, cfg, session: 2)

    result = WafReconcileBansCmd(db_session=db_session).call()

    assert sorted(loaded) == ["broken", "good"]
    errors = [r for r in result if r["t"] == "error"]
    assert len(errors) == 1
    assert "broken: hop3.toml: invalid TOML at line 3" in errors[0]["text"]
    assert "1 of 2 WAF-enabled app(s); 2 active ban(s)" in result[0]["text"]


def test_no_error_when_every_waf_app_is_scored(db_session, monkeypatch):
    db_session.add(App(name="good", waf_port=4001))
    db_session.commit()
    monkeypatch.setattr(AppConfig, "from_dir", staticmethod(lambda p: object()))
    monkeypatch.setattr(waf_cmd, "reconcile_bans", lambda app, cfg, session: 0)

    result = WafReconcileBansCmd(db_session=db_session).call()

    assert all(r["t"] != "error" for r in result)
