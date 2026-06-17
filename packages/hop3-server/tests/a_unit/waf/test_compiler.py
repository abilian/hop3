# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Compiler: [waf] policy -> SecLang (ADR 048). Pure tests, no engine needed."""

from __future__ import annotations

import pytest

from hop3.project.schema import validate_hop3_toml
from hop3.waf.compiler import WafCompileError, compile_policy

NETS = {"office": ["203.0.113.0/24", "10.0.0.0/8"]}


def _policy(waf: dict):
    return validate_hop3_toml({"waf": waf}).waf


def test_enabled_only_emits_just_the_engine_directive():
    out = compile_policy("app", _policy({"enabled": True}), {})
    assert "SecRuleEngine On" in out
    assert "SecRule " not in out


def test_detect_mode_uses_nondisruptive_action():
    out = compile_policy(
        "app", _policy({"enabled": True, "mode": "detect", "allow": ["/"]}), {}
    )
    assert "SecRuleEngine On" in out
    assert "phase:1,pass,log" in out
    assert "deny,status:403" not in out


def test_allow_emits_negated_anchored_regex_deny():
    out = compile_policy(
        "app", _policy({"enabled": True, "allow": ["/", "/api/.*"]}), {}
    )
    assert 'SecRule REQUEST_URI "!@rx ^(?:/|/api/.*)$"' in out
    assert "phase:1,deny,status:403,log" in out


def test_gate_emits_chain_with_ipmatch_cidr_list():
    out = compile_policy(
        "app", _policy({"gate": [{"paths": ["/admin/.*"], "require": "office"}]}), NETS
    )
    assert 'SecRule REQUEST_URI "@rx ^(?:/admin/.*)$"' in out
    assert "phase:1,chain,deny,status:403,log" in out
    assert 'SecRule REMOTE_ADDR "!@ipMatch 203.0.113.0/24,10.0.0.0/8"' in out


def test_gate_unknown_network_fails_loud():
    with pytest.raises(WafCompileError, match="network 'ghost'"):
        compile_policy(
            "app", _policy({"gate": [{"paths": ["/admin/.*"], "require": "ghost"}]}), {}
        )


def test_tuning_disable_rule_ids_is_path_scoped_ctl():
    out = compile_policy(
        "app",
        _policy({
            "tuning": [{"paths": ["/admin/.*"], "disable-rule-ids": [941100, 942100]}]
        }),
        {},
    )
    assert 'SecRule REQUEST_URI "@rx ^(?:/admin/.*)$"' in out
    assert "ctl:ruleRemoveById=941100,ctl:ruleRemoveById=942100" in out


def test_tuning_without_paths_uses_global_directive():
    out = compile_policy(
        "app", _policy({"tuning": [{"disable-rule-ids": [941100]}]}), {}
    )
    assert "SecRuleRemoveById 941100" in out


def test_tuning_skip_body_inspection_fails_loud():
    with pytest.raises(WafCompileError, match="skip-body-inspection"):
        compile_policy(
            "app",
            _policy({"tuning": [{"paths": ["/x"], "skip-body-inspection": True}]}),
            {},
        )


def test_output_ends_with_newline():
    assert compile_policy("app", _policy({"enabled": True}), {}).endswith("\n")
