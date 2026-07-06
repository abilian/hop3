# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Compiler: [waf] policy -> SecLang (ADR 050). Pure tests, no engine needed."""

from __future__ import annotations

import pytest

from hop3.project.schema import validate_hop3_toml
from hop3.waf import crs_dir
from hop3.waf.compiler import (
    WafCompileError,
    compile_bans,
    compile_policy,
    compile_rules_file,
)

NETS = {"office": ["203.0.113.0/24", "10.0.0.0/8"]}


def _fake_crs(tmp_path):
    """A minimal CRS dir: just the files whose ordering the compiler pins."""
    for name in ("REQUEST-901-INITIALIZATION", "REQUEST-942-SQLI", "REQUEST-949-BLK"):
        (tmp_path / f"{name}.conf").write_text("# stub\n")
    return tmp_path


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
    assert 'SecRule REQUEST_FILENAME "!@rx ^(?:/|/api/.*)$"' in out
    assert "phase:1,deny,status:403,log" in out
    # path is canonicalized before matching (Security invariant 2).
    assert "t:none,t:urlDecodeUni,t:normalizePath" in out


def test_gate_emits_chain_with_ipmatch_cidr_list():
    out = compile_policy(
        "app", _policy({"gate": [{"paths": ["/admin/.*"], "require": "office"}]}), NETS
    )
    assert 'SecRule REQUEST_FILENAME "@rx ^(?:/admin/.*)$"' in out
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
    assert 'SecRule REQUEST_FILENAME "@rx ^(?:/admin/.*)$"' in out
    assert "ctl:ruleRemoveById=941100,ctl:ruleRemoveById=942100" in out


def test_tuning_without_paths_uses_global_directive():
    out = compile_policy(
        "app", _policy({"tuning": [{"disable-rule-ids": [941100]}]}), {}
    )
    assert "SecRuleRemoveById 941100" in out


def test_tuning_skip_body_inspection_emits_ctl():
    out = compile_policy(
        "app",
        _policy({"tuning": [{"paths": ["/dav/.*"], "skip-body-inspection": True}]}),
        {},
    )
    assert 'SecRule REQUEST_FILENAME "@rx ^(?:/dav/.*)$"' in out
    assert "ctl:requestBodyAccess=Off" in out


def test_tuning_global_skip_body_inspection_is_unconditional_ctl():
    out = compile_policy(
        "app", _policy({"tuning": [{"skip-body-inspection": True}]}), {}
    )
    assert 'SecAction "id:' in out
    assert "ctl:requestBodyAccess=Off" in out


def test_tuning_combines_disable_ids_and_body_skip():
    out = compile_policy(
        "app",
        _policy({
            "tuning": [
                {
                    "paths": ["/dav/.*"],
                    "disable-rule-ids": [920420],
                    "skip-body-inspection": True,
                }
            ]
        }),
        {},
    )
    assert "ctl:ruleRemoveById=920420" in out
    assert "ctl:requestBodyAccess=Off" in out


def test_output_ends_with_newline():
    assert compile_policy("app", _policy({"enabled": True}), {}).endswith("\n")


# --- compile_rules_file: CRS baseline + overlay ---------------------------


def test_rules_file_includes_crs_setup_and_ordered_request_files(tmp_path):
    out = compile_rules_file(
        "app", _policy({"enabled": True, "allow": ["/"]}), {}, _fake_crs(tmp_path)
    )
    # crs-setup SecAction precedes the first Include.
    assert "id:900000" in out
    includes = [line for line in out.splitlines() if line.startswith("Include ")]
    assert includes[0].endswith("REQUEST-901-INITIALIZATION.conf")  # 901 first
    assert includes[-1].endswith("REQUEST-949-BLK.conf")  # 949 last
    # the access overlay is still appended after the CRS baseline.
    assert "path not permitted" in out


def test_rules_file_paranoia_level_is_reflected(tmp_path):
    out = compile_rules_file(
        "app", _policy({"enabled": True, "paranoia": 3}), {}, _fake_crs(tmp_path)
    )
    assert "setvar:tx.blocking_paranoia_level=3" in out
    assert "setvar:tx.detection_paranoia_level=3" in out


def test_rules_file_missing_crs_bundle_fails_loud(tmp_path):
    with pytest.raises(WafCompileError, match="CRS bundle"):
        compile_rules_file(
            "app", _policy({"enabled": True}), {}, tmp_path / "does-not-exist"
        )


def test_rules_file_non_crs_ruleset_emits_no_includes(tmp_path):
    out = compile_rules_file(
        "app", _policy({"enabled": True, "ruleset": "none"}), {}, _fake_crs(tmp_path)
    )
    assert "Include " not in out
    assert "id:900000" not in out


def test_rules_file_against_vendored_crs_bundle():
    """The real vendored bundle resolves and embeds via the locator."""
    out = compile_rules_file("app", _policy({"enabled": True}), {}, crs_dir())
    assert "REQUEST-901-INITIALIZATION.conf" in out
    assert "REQUEST-949-BLOCKING-EVALUATION.conf" in out


# --- compile_bans (L7 denylist) -------------------------------------------


def test_compile_bans_empty_is_header_only():
    out = compile_bans([])
    assert "SecRule" not in out
    assert out.endswith("\n")


def test_compile_bans_emits_ipmatch_deny():
    out = compile_bans(["198.51.100.9", "203.0.113.7"])
    assert 'SecRule REMOTE_ADDR "@ipMatch 198.51.100.9,203.0.113.7"' in out
    assert "deny,status:403" in out


# --- ADR worked examples compile end-to-end -------------------------------


def test_wordpress_worked_example_compiles():
    waf = {
        "enabled": True,
        "mode": "block",
        "ruleset": "owasp-crs",
        "gate": [{"paths": ["/wp-admin/.*", "/wp-login\\.php"], "require": "office"}],
        "tuning": [
            {"paths": ["/wp-admin/.*"], "disable-rule-ids": [941100, 941160, 942100]}
        ],
        "bans": {"enabled": True, "threshold": 8, "window": "10m", "duration": "1h"},
    }
    out = compile_rules_file(
        "wp", _policy(waf), {"office": ["203.0.113.0/24"]}, crs_dir()
    )
    assert "@ipMatch 203.0.113.0/24" in out
    assert "ctl:ruleRemoveById=941100" in out


def test_nextcloud_worked_example_compiles():
    waf = {
        "enabled": True,
        "mode": "block",
        "ruleset": "owasp-crs",
        "tuning": [
            {
                "paths": ["/remote.php/dav/.*", "/remote.php/webdav/.*"],
                "skip-body-inspection": True,
                "disable-rule-ids": [911100, 920420, 920470],
            }
        ],
        "bans": {"enabled": True, "threshold": 6, "window": "10m", "duration": "2h"},
    }
    out = compile_rules_file("nc", _policy(waf), {}, crs_dir())
    assert "ctl:requestBodyAccess=Off" in out
    assert "ctl:ruleRemoveById=920420" in out
