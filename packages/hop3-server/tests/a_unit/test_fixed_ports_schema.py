# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Schema + parsing for the [[ports]] section (fixed host ports).

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
    assert cfg.ports == [{"number": 1935, "protocol": "tcp", "name": "rtmp"}]


def test_protocol_defaults_to_tcp():
    cfg = Hop3Config.from_str("[[ports]]\nnumber = 25\n")
    assert cfg.ports[0]["protocol"] == "tcp"


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
    ],
)
def test_invalid_ports_rejected(toml):
    with pytest.raises(Hop3TomlValidationError):
        validate_hop3_toml(tomllib.loads(toml))
