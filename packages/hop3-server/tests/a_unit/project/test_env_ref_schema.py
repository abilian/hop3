# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Schema + parsing for [env] dynamic references (ADR 046 §1b).

A reference (`{ from, key }`, `{ key }`, or `{ external_ip = true }`) must parse
into ``Hop3Config.env_refs`` and validate its shape; a malformed reference — or
any unrecognised table value under [env] — must fail loud, not be dropped.
"""

from __future__ import annotations

import pytest
import tomllib

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def test_refs_are_exposed_via_env_refs():
    cfg = Hop3Config.from_str(
        "[env]\n"
        'DB = { from = "database", key = "DATABASE_URL" }\n'
        'FQDN = { key = "domain" }\n'
        "IP = { external_ip = true }\n"
    )
    assert cfg.env_refs == {
        "DB": {"from": "database", "key": "DATABASE_URL"},
        "FQDN": {"key": "domain"},
        "IP": {"external_ip": True},
    }


def test_refs_excluded_from_plain_env_and_generated():
    cfg = Hop3Config.from_str(
        '[env]\nDEBUG = "false"\nFQDN = { key = "domain" }\n'
        'SECRET = { generate = "hex" }\n'
    )
    assert cfg.env == {"DEBUG": "false"}
    assert set(cfg.env_refs) == {"FQDN"}
    assert set(cfg.env_generated) == {"SECRET"}


def test_computed_subtable_is_not_a_ref():
    cfg = Hop3Config.from_str('[env]\n[env.computed]\nU = "${HOST}"\n')
    assert cfg.env_refs == {}


def test_valid_refs_pass():
    toml = (
        "[env]\n"
        'A = { from = "db", key = "DATABASE_URL" }\n'
        'B = { key = "hostname" }\n'
        "C = { external_ip = true }\n"
    )
    validate_hop3_toml(tomllib.loads(toml))  # must not raise


@pytest.mark.parametrize(
    "toml",
    [
        '[env]\nX = { from = "db" }',  # `from` without `key`
        '[env]\nX = { external_ip = true, key = "domain" }',  # mutually exclusive
        '[env]\nX = { key = "domain", bogus = 1 }',  # unknown field (extra=forbid)
        "[env]\nX = { }",  # empty table — neither generate nor ref
        "[env]\nX = { foo = 1 }",  # unrecognised table shape (fail loud)
    ],
)
def test_malformed_or_unknown_tables_rejected(toml):
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml(tomllib.loads(toml))
