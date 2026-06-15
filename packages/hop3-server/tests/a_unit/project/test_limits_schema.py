# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Schema + parsing for the [limits] section (resource caps, ADR 046 §3)."""

from __future__ import annotations

import pytest
import tomllib

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def test_limits_parse():
    cfg = Hop3Config.from_str('[limits]\nmemory = "512M"\ncpu = 1.5\nprocesses = 256\n')
    assert cfg.limits == {"memory": "512M", "cpu": 1.5, "processes": 256}


def test_no_limits_is_empty():
    assert Hop3Config.from_str('[metadata]\nid = "x"\n').limits == {}


def test_partial_limits_only_set_fields():
    assert Hop3Config.from_str('[limits]\nmemory = "1G"\n').limits == {"memory": "1G"}


@pytest.mark.parametrize(
    "toml",
    [
        '[limits]\nmemory = "512M"',
        '[limits]\nmemory = "536870912"',  # plain bytes
        "[limits]\ncpu = 2",
        "[limits]\ncpu = 0.5",
        "[limits]\nprocesses = 100",
    ],
)
def test_valid_limits_pass(toml):
    validate_hop3_toml(tomllib.loads(toml))  # must not raise


@pytest.mark.parametrize(
    "toml",
    [
        '[limits]\nmemory = "512MB"',  # unsupported suffix
        '[limits]\nmemory = "1.5G"',  # fractional + suffix
        "[limits]\ncpu = 0",  # must be > 0
        "[limits]\ncpu = -1",
        "[limits]\nprocesses = 0",  # must be >= 1
        "[limits]\nbogus = 1",  # unknown field (extra=forbid)
    ],
)
def test_invalid_limits_rejected(toml):
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml(tomllib.loads(toml))
