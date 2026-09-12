# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Schema + parsing for the [proxy] section (per-app transfer limits)."""

from __future__ import annotations

import pytest
import tomllib

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def test_proxy_parse():
    cfg = Hop3Config.from_str(
        '[proxy]\nmax-body-size = "2G"\nrequest-buffering = false\n'
    )
    assert cfg.proxy_max_body_size == "2G"
    assert cfg.proxy_request_buffering is False


def test_no_proxy_section_leaves_platform_defaults():
    cfg = Hop3Config.from_str('[metadata]\nid = "x"\n')
    assert cfg.proxy_max_body_size == ""
    assert cfg.proxy_request_buffering is True


def test_buffering_declared_on_stays_on():
    cfg = Hop3Config.from_str("[proxy]\nrequest-buffering = true\n")
    assert cfg.proxy_request_buffering is True


@pytest.mark.parametrize(
    "toml",
    [
        '[proxy]\nmax-body-size = "50m"',
        '[proxy]\nmax-body-size = "2G"',
        '[proxy]\nmax-body-size = "0"',  # nginx spelling for "no limit"
        '[proxy]\nmax-body-size = "2147483648"',  # plain bytes
        "[proxy]\nrequest-buffering = false",
    ],
)
def test_valid_proxy_pass(toml):
    validate_hop3_toml(tomllib.loads(toml))  # must not raise


@pytest.mark.parametrize(
    "toml",
    [
        '[proxy]\nmax-body-size = "2GB"',  # unsupported suffix
        '[proxy]\nmax-body-size = "1.5G"',  # fractional
        '[proxy]\nmax-body-size = "2 G"',  # space
        '[proxy]\nmax-body-size = "unlimited"',
        '[proxy]\nrequest-buffering = "off"',  # bool, not a string
        '[proxy]\nmaxbodysize = "2G"',  # unknown key
    ],
)
def test_invalid_proxy_rejected(toml):
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml(tomllib.loads(toml))


@pytest.mark.parametrize(
    "value",
    [
        "2G;\n  root /etc;",  # nginx directive injection
        "2G\n}\nserver {",
        "50m; deny all",
    ],
)
def test_max_body_size_cannot_inject_proxy_directives(value):
    """
    The value lands in `client_max_body_size $VALUE;` — un-validated, a
    newline or `;` would append directives of the caller's choosing.
    """
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml({"proxy": {"max-body-size": value}})
