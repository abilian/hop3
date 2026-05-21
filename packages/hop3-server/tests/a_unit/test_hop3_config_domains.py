# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the [domains] section: schema validation and Hop3Config getters."""

from __future__ import annotations

import pytest

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def test_valid_domains_parsed():
    cfg = Hop3Config.from_str(
        """
[domains]
list = ["abilian.com", "www.abilian.com"]
"""
    )
    assert cfg.domains == ["abilian.com", "www.abilian.com"]
    assert cfg.domains_policy == "keep-existing"


def test_override_policy():
    cfg = Hop3Config.from_str(
        """
[domains]
list = ["abilian.com"]
_policy = "override"
"""
    )
    assert cfg.domains_policy == "override"


def test_no_section_returns_empty_defaults():
    cfg = Hop3Config.from_str('[metadata]\nid = "a"')
    assert cfg.domains == []
    assert cfg.domains_policy == "keep-existing"


def test_empty_list_parses():
    """list = [] is valid schema-wise; deployer treats it as no-op."""
    cfg = Hop3Config.from_str(
        """
[domains]
list = []
"""
    )
    assert cfg.domains == []


def test_catch_all_alone_ok():
    validate_hop3_toml({"domains": {"list": ["_"]}})


def test_catch_all_mixed_rejected():
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"domains": {"list": ["_", "example.com"]}})
    assert "catch-all" in str(exc.value).lower()


def test_env_hostname_and_domains_mutually_exclusive():
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({
            "env": {"HOST_NAME": "a.com"},
            "domains": {"list": ["b.com"]},
        })
    msg = str(exc.value)
    assert "HOST_NAME" in msg
    assert "[domains]" in msg


def test_env_hostname_alone_still_valid():
    """Legacy apps using HOST_NAME in [env] must keep working."""
    validate_hop3_toml({"env": {"HOST_NAME": "legacy.example.com"}})


def test_invalid_policy_rejected():
    with pytest.raises(Hop3TomlValidationError) as exc:
        validate_hop3_toml({"domains": {"list": ["a.com"], "_policy": "bogus"}})
    assert "_policy" in str(exc.value).lower() or "policy" in str(exc.value).lower()


def test_missing_list_rejected():
    """[domains] without `list` is a schema error."""
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml({"domains": {}})


def test_policy_filtered_from_section_getter():
    """The `_policy` key is internal — not surfaced via domains getter."""
    cfg = Hop3Config.from_str(
        """
[domains]
list = ["a.com"]
_policy = "override"
"""
    )
    assert cfg.domains == ["a.com"]  # no "_policy" leaking through
