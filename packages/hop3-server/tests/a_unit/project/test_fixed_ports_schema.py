# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Schema + parsing for the [[ports]] section (fixed host ports).

Declared fixed ports (SMTP/XMPP/RTMP/federation, …) are the input to the
host-wide claim registry; this guards that the schema parses valid entries and
rejects malformed ones before they ever reach the deployer.
"""

from __future__ import annotations

import pytest
import tomllib

from hop3.project.hop3_config import Hop3Config
from hop3.project.schema import Hop3TomlValidationError, validate_hop3_toml


def test_parses_ports():
    cfg = Hop3Config.from_str(
        '[[ports]]\nnumber = 1935\nprotocol = "tcp"\nname = "rtmp"\n'
    )
    assert cfg.ports == [
        {"number": 1935, "protocol": "tcp", "name": "rtmp", "source": "any"}
    ]


def test_protocol_defaults_to_tcp():
    cfg = Hop3Config.from_str("[[ports]]\nnumber = 25\n")
    assert cfg.ports[0]["protocol"] == "tcp"


def test_source_defaults_to_any():
    cfg = Hop3Config.from_str("[[ports]]\nnumber = 25\n")
    assert cfg.ports[0]["source"] == "any"


def test_source_cidr_is_parsed():
    cfg = Hop3Config.from_str('[[ports]]\nnumber = 5432\nsource = "10.0.0.0/8"\n')
    assert cfg.ports[0]["source"] == "10.0.0.0/8"


def test_source_cidr_is_canonicalised_by_validator():
    # validate_hop3_toml canonicalises a host-bearing CIDR to its network form.
    schema = validate_hop3_toml(
        tomllib.loads('[[ports]]\nnumber = 5432\nsource = "10.0.0.5/8"')
    )
    assert schema.ports is not None
    assert schema.ports[0].source == "10.0.0.0/8"


def test_no_ports_section_is_empty_list():
    assert Hop3Config.from_str('[metadata]\nid = "x"\n').ports == []


@pytest.mark.parametrize(
    "toml",
    [
        "[[ports]]\nnumber = 0",  # below range
        "[[ports]]\nnumber = 70000",  # above range
        "[[ports]]\nnumber = 80",  # reserved (nginx)
        "[[ports]]\nnumber = 443",  # reserved (nginx)
        "[[ports]]\nnumber = 22",  # reserved (ssh)
        '[[ports]]\nnumber = 25\nprotocol = "sctp"',  # bad protocol
        "[[ports]]\nnumber = 25\nextra = 1",  # unknown field (extra=forbid)
        "[[ports]]\nnumber = 25\n[[ports]]\nnumber = 25",  # duplicate (number, proto)
        '[[ports]]\nnumber = 25\nsource = "not-a-cidr"',  # bad source
        '[[ports]]\nnumber = 25\nsource = "10.0.0.0/33"',  # impossible prefix
        '[[ports]]\nnumber = 25\nsource = "2001:db8::/32"',  # IPv6 unsupported
    ],
)
def test_invalid_ports_rejected(toml):
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml(tomllib.loads(toml))
