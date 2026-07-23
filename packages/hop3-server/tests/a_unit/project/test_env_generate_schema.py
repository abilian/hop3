# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Schema + parsing for [env] { generate = ... } secret declarations (ADR 046).

A generated secret declared in hop3.toml must parse into
``Hop3Config.env_generated`` (and stay out of the plain ``env`` getter, which
drops dict values), and a malformed generate spec must fail loud at validation
rather than silently producing a bad secret.
"""

from __future__ import annotations

import pytest
import tomllib

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def test_generate_table_is_exposed_via_env_generated():
    cfg = Hop3Config.from_str(
        '[env]\nSECRET_KEY_BASE = { generate = "hex", length = 64 }\n'
    )
    assert cfg.env_generated == {"SECRET_KEY_BASE": {"generate": "hex", "length": 64}}


def test_generate_table_excluded_from_plain_env():
    # The static `env` getter drops dict values; generation flows separately.
    cfg = Hop3Config.from_str(
        '[env]\nDEBUG = "false"\nAPP_KEY = { generate = "base64" }\n'
    )
    assert cfg.env == {"DEBUG": "false"}
    assert "APP_KEY" in cfg.env_generated


def test_no_generate_is_empty():
    assert Hop3Config.from_str('[env]\nDEBUG = "false"\n').env_generated == {}


def test_computed_subtable_is_not_a_generate():
    cfg = Hop3Config.from_str('[env]\n[env.computed]\nURL = "${HOST}"\n')
    assert cfg.env_generated == {}


def test_valid_generate_specs_pass():
    toml = (
        "[env]\n"
        'A = { generate = "hex", length = 64 }\n'
        'B = { generate = "base64", length = 32, prefix = "base64:" }\n'
        'C = { generate = "password", length = 24, display = true }\n'
        'D = { generate = "uuid" }\n'
        'E = { generate = "urlsafe" }\n'
    )
    validate_hop3_toml(tomllib.loads(toml))  # must not raise


@pytest.mark.parametrize(
    "toml",
    [
        '[env]\nX = { generate = "md5" }',  # unknown generator
        '[env]\nX = { generate = "hex", length = 0 }',  # length < 1
        '[env]\nX = { generate = "hex", bogus = 1 }',  # unknown field (extra=forbid)
    ],
)
def test_malformed_generate_rejected(toml):
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml(tomllib.loads(toml))
