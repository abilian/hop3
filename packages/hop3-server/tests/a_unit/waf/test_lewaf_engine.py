# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
LeWAF engine plugin (ADR 050): config generation + registration.

No `lewaf` import here — the engine's config generation is engine-independent
(it writes SecLang), so these run on any Python (no waf extra needed).
"""

from __future__ import annotations

import importlib
import sys
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


def test_configure_app_writes_proxy_yaml_config(tmp_path: Path):
    engine = LeWafEngine(rules_dir=tmp_path)
    engine.configure_app("myapp", _policy({"enabled": True}), {})
    config = tmp_path / "myapp.yaml"
    assert config.exists()
    # YAML points the proxy's rule_files loader at the compiled .conf.
    assert str(tmp_path / "myapp.conf") in config.read_text()


def test_remove_app_deletes_rules_and_config(tmp_path: Path):
    engine = LeWafEngine(rules_dir=tmp_path)
    engine.configure_app("myapp", _policy({"enabled": True}), {})
    engine.remove_app("myapp")
    assert not (tmp_path / "myapp.conf").exists()
    assert not (tmp_path / "myapp.yaml").exists()


def test_remove_app_is_idempotent(tmp_path: Path):
    LeWafEngine(rules_dir=tmp_path).remove_app("never-configured")  # must not raise


def test_plugin_registers_the_engine():
    assert LeWafEngine in LeWafPlugin().get_waf_engines()


def test_proxy_command_uses_yaml_config_and_trusted_proxy(tmp_path: Path):
    cmd = LeWafEngine(rules_dir=tmp_path).proxy_command(
        "myapp", "http://127.0.0.1:8000", 9000
    )
    assert "hop3.plugins.waf.lewaf._proxy_main" in cmd
    assert "--upstream" in cmd
    assert "http://127.0.0.1:8000" in cmd
    # routed via the YAML config (the only path that loads the CRS), not --rules-file
    assert str(tmp_path / "myapp.yaml") in cmd
    assert "--rules-file" not in cmd
    # real client IP from the single nginx hop (Security invariant 1)
    assert cmd[cmd.index("--trusted-proxy-count") + 1] == "1"


def test_proxy_main_has_no_eager_optional_imports(monkeypatch):
    """
    scan_package('hop3.plugins') imports this module on every server start;
    lewaf/uvicorn (the waf extra, 3.12+) must not be needed at import time.
    """
    monkeypatch.setitem(sys.modules, "lewaf", None)
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    sys.modules.pop("hop3.plugins.waf.lewaf._proxy_main", None)
    importlib.import_module("hop3.plugins.waf.lewaf._proxy_main")  # must not raise


def test_write_bans_only_rewrites_on_change(tmp_path: Path):
    """
    The scorer runs on a frequent timer, so an unchanged denylist must be a
    no-op (return False) — otherwise every cycle would churn the proxy.
    """
    engine = LeWafEngine(rules_dir=tmp_path)
    assert engine.write_bans("app", ["198.51.100.9"]) is True  # created
    assert engine.write_bans("app", ["198.51.100.9"]) is False  # unchanged
    assert engine.write_bans("app", ["198.51.100.9", "203.0.113.1"]) is True  # changed
