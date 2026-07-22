# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Behavioral proof that the compiled SecLang parses and enforces in the real
engine. Skips when the optional ``lewaf`` extra isn't installed (needs Python
>= 3.12). The slice-3 equivalent of the compile-before-commit dry-run (ADR 050
§5), now covering gates (chain + @ipMatch list) on lewaf >= 0.7.5."""

from __future__ import annotations

import pytest

from hop3.project.schema import validate_hop3_toml
from hop3.waf.compiler import compile_policy

pytest.importorskip("lewaf")

NETS = {"office": ["203.0.113.0/24", "10.0.0.0/8"]}


def _policy(waf: dict):
    return validate_hop3_toml({"waf": waf}).waf


def _blocked(rules_text: str, path: str, ip: str | None = None) -> bool:
    """Run a request through a real LeWAF transaction; True if it was blocked."""
    from lewaf.integration import WAF  # ruff:ignore[import-outside-top-level]
    from lewaf.seclang.parser import (
        SecLangParser,
    )

    waf = WAF()
    SecLangParser(waf).from_string(rules_text)
    tx = waf.new_transaction()
    tx.process_uri(path, "GET")
    if ip:
        tx.variables.remote_addr.set(ip)
    return bool(tx.process_request_headers() or tx.process_request_body())


def test_compiled_allowlist_enforces_default_deny():
    rules = compile_policy(
        "app", _policy({"enabled": True, "allow": ["/", "/api/.*"]}), {}
    )
    assert _blocked(rules, "/") is False
    assert _blocked(rules, "/api/v1/users") is False
    assert _blocked(rules, "/wp-admin") is True
    assert _blocked(rules, "/.env") is True


def test_allow_full_match_does_not_over_match():
    rules = compile_policy("app", _policy({"enabled": True, "allow": ["/api"]}), {})
    assert _blocked(rules, "/api") is False
    assert _blocked(rules, "/api-internal") is True


def test_detect_mode_logs_but_does_not_block():
    rules = compile_policy(
        "app", _policy({"enabled": True, "mode": "detect", "allow": ["/"]}), {}
    )
    assert _blocked(rules, "/wp-admin") is False


def test_gate_blocks_outside_network_allows_inside():
    # chain (path AND not-in-network) + @ipMatch CIDR list — both need lewaf >= 0.7.5.
    rules = compile_policy(
        "app",
        _policy({"gate": [{"paths": ["/admin(?:/.*)?"], "require": "office"}]}),
        NETS,
    )
    assert _blocked(rules, "/admin", "8.8.8.8") is True  # outside both CIDRs -> block
    assert _blocked(rules, "/admin", "203.0.113.5") is False  # inside 1st CIDR -> allow
    assert _blocked(rules, "/admin/x", "10.9.9.9") is False  # inside 2nd CIDR -> allow
    assert _blocked(rules, "/public", "8.8.8.8") is False  # non-gate path -> allow


def test_full_policy_parses():
    # allow + gate + tuning(disable-rule-ids) must produce valid SecLang.
    from lewaf.integration import WAF  # ruff:ignore[import-outside-top-level]
    from lewaf.seclang.parser import (
        SecLangParser,
    )

    rules = compile_policy(
        "app",
        _policy({
            "allow": ["/", "/api/.*"],
            "gate": [{"paths": ["/admin/.*"], "require": "office"}],
            "tuning": [{"paths": ["/api/.*"], "disable-rule-ids": [942100]}],
        }),
        NETS,
    )
    SecLangParser(WAF()).from_string(rules)  # raises if the SecLang is invalid
