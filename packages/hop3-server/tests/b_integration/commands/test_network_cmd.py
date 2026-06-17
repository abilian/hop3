# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 network` — operator-defined named networks for WAF gates (ADR 048 §2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.commands.network import NetworkAddCmd, NetworkListCmd, NetworkRmCmd
from hop3.orm import NetworkRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _add(db_session: Session, *args):
    return NetworkAddCmd(db_session=db_session).call(*args)


def test_empty_list(db_session: Session):
    out = NetworkListCmd(db_session=db_session).call()
    assert out[0]["t"] == "text"
    assert "No named networks" in out[0]["text"]


def test_add_then_list(db_session: Session):
    _add(db_session, "office", "203.0.113.0/24", "10.0.0.0/8")
    net = NetworkRepository(session=db_session).get_by_name("office")
    assert net is not None
    assert net.cidrs == ["203.0.113.0/24", "10.0.0.0/8"]

    out = NetworkListCmd(db_session=db_session).call()
    assert out[0]["t"] == "table"
    assert out[0]["rows"] == [["office", "203.0.113.0/24, 10.0.0.0/8"]]


def test_add_canonicalises_cidr(db_session: Session):
    _add(db_session, "vpn", "10.8.0.5/24")  # host bits set
    net = NetworkRepository(session=db_session).get_by_name("vpn")
    assert net.cidrs == ["10.8.0.0/24"]


def test_add_accepts_ipv6(db_session: Session):
    # WAF gates are L7 (SecLang @ipMatch) — unlike the rootd firewall, v6 is fine.
    _add(db_session, "v6", "fd00::/8")
    assert NetworkRepository(session=db_session).get_by_name("v6").cidrs == ["fd00::/8"]


def test_re_add_replaces_cidrs(db_session: Session):
    _add(db_session, "office", "203.0.113.0/24")
    _add(db_session, "office", "198.51.100.0/24")
    net = NetworkRepository(session=db_session).get_by_name("office")
    assert net.cidrs == ["198.51.100.0/24"]  # replaced, not appended
    # Still a single row (unique on name).
    assert len(list(NetworkRepository(session=db_session).get_many())) == 1


def test_add_rejects_bad_cidr(db_session: Session):
    out = _add(db_session, "office", "not-a-cidr")
    assert out[0]["t"] == "error"
    assert NetworkRepository(session=db_session).get_by_name("office") is None


def test_add_rejects_reserved_name(db_session: Session):
    out = _add(db_session, "auth", "10.0.0.0/8")
    assert out[0]["t"] == "error"
    assert "reserved" in out[0]["text"]


def test_add_rejects_bad_name(db_session: Session):
    out = _add(db_session, "has spaces", "10.0.0.0/8")
    assert out[0]["t"] == "error"


def test_rm(db_session: Session):
    _add(db_session, "office", "10.0.0.0/8")
    out = NetworkRmCmd(db_session=db_session).call("office")
    assert out[0]["t"] == "text"
    assert "Removed" in out[0]["text"]
    assert NetworkRepository(session=db_session).get_by_name("office") is None


def test_rm_unknown_is_an_error(db_session: Session):
    out = NetworkRmCmd(db_session=db_session).call("ghost")
    assert out[0]["t"] == "error"


def test_add_usage_when_no_cidrs(db_session: Session):
    out = _add(db_session, "office")
    assert out[0]["t"] == "text"
    assert "Usage" in out[0]["text"]


def test_list_rejects_stray_args(db_session: Session):
    with pytest.raises(ValueError, match="takes no arguments"):
        NetworkListCmd(db_session=db_session).call("extra")
