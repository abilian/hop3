# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Schema + parsing for the [waf] section (ADR 048, Layer-7 WAF).

The [waf] block is the engine-independent declarative surface; this guards that
valid policy parses and malformed policy is rejected at hop3.toml load — before
anything is compiled to the engine or deployed. Two security-critical behaviours
are asserted explicitly: `require = "auth"` fails loud (forward-auth not yet
available), and bad path regexes are caught at deploy, not at request time.
"""

from __future__ import annotations

import pytest
import tomllib

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def test_no_waf_section_is_empty():
    assert Hop3Config.from_str('[metadata]\nid = "x"\n').waf == {}


def test_minimal_waf_parses_and_defaults():
    cfg = Hop3Config.from_str("[waf]\nenabled = true\n")
    schema = validate_hop3_toml({"waf": {"enabled": True}})
    assert cfg.waf == {"enabled": True}
    assert schema.waf is not None
    assert schema.waf.enabled is True
    assert schema.waf.mode == "block"
    assert schema.waf.ruleset == "owasp-crs"
    assert schema.waf.paranoia == 1


def test_disabled_by_default():
    schema = validate_hop3_toml({"waf": {}})
    assert schema.waf is not None
    assert schema.waf.enabled is False


def test_positive_model_allowlist_parses():
    schema = validate_hop3_toml({
        "waf": {"enabled": True, "allow": ["/", "/static/.*", "/api/.*"]}
    })
    assert schema.waf.allow == ["/", "/static/.*", "/api/.*"]


def test_gate_with_named_network_parses():
    schema = validate_hop3_toml({
        "waf": {"gate": [{"paths": ["/admin/.*"], "require": "office"}]}
    })
    assert schema.waf.gate[0].require == "office"
    assert schema.waf.gate[0].paths == ["/admin/.*"]


def test_gate_require_auth_is_rejected():
    # Security: forward-auth doesn't exist yet — must fail loud, never silently allow.
    with pytest.raises(Hop3TomlValidationError, match="forward-auth"):
        validate_hop3_toml({
            "waf": {"gate": [{"paths": ["/admin/.*"], "require": "auth"}]}
        })


def test_tuning_parses_with_hyphenated_keys():
    schema = validate_hop3_toml({
        "waf": {
            "tuning": [
                {
                    "paths": ["/admin/.*"],
                    "disable-rule-ids": [941100, 942100],
                    "reason": "editor",
                }
            ]
        }
    })
    assert schema.waf.tuning[0].disable_rule_ids == [941100, 942100]


def test_bans_parse():
    schema = validate_hop3_toml({
        "waf": {
            "bans": {"enabled": True, "threshold": 8, "window": "10m", "duration": "1h"}
        }
    })
    assert schema.waf.bans.threshold == 8
    assert schema.waf.bans.duration == "1h"


@pytest.mark.parametrize(
    "waf",
    [
        {"mode": "warn"},  # bad mode
        {"paranoia": 0},  # below range
        {"paranoia": 5},  # above range
        {"allow": []},  # empty allowlist = deny everything (typo)
        {"allow": ["("]},  # invalid regex
        {"gate": [{"paths": [], "require": "office"}]},  # gate without paths
        {"gate": [{"paths": ["["], "require": "office"}]},  # bad regex in gate
        {"gate": [{"paths": ["/x"]}]},  # gate missing require
        {"tuning": [{"paths": ["/x"]}]},  # tuning relaxes nothing
        {"tuning": [{"paths": ["("], "skip-body-inspection": True}]},  # bad regex
        {"bans": {"threshold": 0}},  # threshold < 1
        {"bans": {"window": "soon"}},  # bad duration
        {"bans": {"duration": "10"}},  # missing unit
        {"unknown": 1},  # extra key (extra=forbid)
    ],
)
def test_invalid_waf_rejected(waf):
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml({"waf": waf})


def test_full_wordpress_example_parses():
    # The ADR 048 WordPress worked example must validate.
    toml = """
[waf]
enabled = true
mode = "block"
ruleset = "owasp-crs"

[[waf.gate]]
paths = ["/wp-admin/.*", "/wp-login\\\\.php"]
require = "office"

[[waf.tuning]]
paths = ["/wp-admin/.*"]
disable-rule-ids = [941100, 941160, 942100, 942200]
reason = "Gutenberg editor posts HTML/JS as admin"

[waf.bans]
enabled = true
threshold = 8
window = "10m"
duration = "1h"
"""
    schema = validate_hop3_toml(tomllib.loads(toml))
    assert schema.waf.enabled is True
    assert schema.waf.gate[0].require == "office"
    assert schema.waf.tuning[0].disable_rule_ids[0] == 941100
    assert schema.waf.bans.duration == "1h"
