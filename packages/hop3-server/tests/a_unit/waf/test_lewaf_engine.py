# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""LeWAF engine plugin (ADR 048): config generation + registration.

No `lewaf` import here — the engine's config generation is engine-independent
(it writes SecLang), so these run on any Python (no waf extra needed)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.plugins.waf.lewaf.engine import LeWafEngine
from hop3.plugins.waf.lewaf.plugin import LeWafPlugin
from hop3.project.schema import validate_hop3_toml

if TYPE_CHECKING:
    from pathlib import Path


def _policy(waf: dict):
    return validate_hop3_toml({"waf": waf}).waf


def test_configure_app_writes_compiled_rules(tmp_path: Path):
    engine = LeWafEngine(rules_dir=tmp_path)
    path = engine.configure_app("myapp", _policy({"allow": ["/", "/api/.*"]}), {})
    assert path == tmp_path / "myapp.conf"
    text = path.read_text()
    assert "SecRuleEngine On" in text
    assert "!@rx ^(?:/|/api/.*)$" in text


def test_configure_app_creates_rules_dir(tmp_path: Path):
    engine = LeWafEngine(rules_dir=tmp_path / "rules")
    engine.configure_app("myapp", _policy({"enabled": True}), {})
    assert (tmp_path / "rules" / "myapp.conf").exists()


def test_configure_app_gate_uses_resolved_networks(tmp_path: Path):
    engine = LeWafEngine(rules_dir=tmp_path)
    path = engine.configure_app(
        "app",
        _policy({"gate": [{"paths": ["/admin/.*"], "require": "office"}]}),
        {"office": ["10.0.0.0/8"]},
    )
    assert "!@ipMatch 10.0.0.0/8" in path.read_text()


def test_remove_app_deletes_rules(tmp_path: Path):
    engine = LeWafEngine(rules_dir=tmp_path)
    engine.configure_app("myapp", _policy({"enabled": True}), {})
    engine.remove_app("myapp")
    assert not (tmp_path / "myapp.conf").exists()


def test_remove_app_is_idempotent(tmp_path: Path):
    LeWafEngine(rules_dir=tmp_path).remove_app("never-configured")  # must not raise


def test_plugin_registers_the_engine():
    assert LeWafEngine in LeWafPlugin().get_waf_engines()
