# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the addon-exposure helper.

The port-claim registry is the real repository on an in-memory database (so
the unique constraint and the rollbacks are exercised); only hop3-rootd and
the addon's connection details are stand-ins.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, ClassVar

import pytest
from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from hop3.deployers import expose
from hop3.deployers.expose import (
    _rewrite_url,
    allocate_public_port,
    connection_url,
    expose_addon,
    unexpose_addon,
)
from hop3.lib import Abort
from hop3.lib.rootd import RootdError
from hop3.orm import PortClaim, PortClaimRepository

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

PG_URL = "postgresql://u:secret@127.0.0.1:5432/mydb"


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    BigIntAuditBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def repo(db_session: Session) -> PortClaimRepository:
    return PortClaimRepository(session=db_session)


class FakeRootd:
    """A rootd client recording every op; ``fail_on`` ops raise RootdError."""

    calls: ClassVar[list[tuple[str, dict]]] = []
    fail_on: ClassVar[set[str]] = set()
    listed_rules: ClassVar[list[dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def call(self, op: str, args: dict) -> dict:
        FakeRootd.calls.append((op, args))
        if op in FakeRootd.fail_on:
            msg = f"{op} boom"
            raise RootdError(msg)
        if op == "firewall.add_rule":
            return {"rule_id": "r1"}
        if op == "proxy.add":
            return {"unit": "u1"}
        if op == "firewall.list_rules":
            return {"rules": FakeRootd.listed_rules}
        return {}


class _Addon:
    def __init__(self, url: str) -> None:
        self.url = url

    def get_connection_details(self) -> dict[str, str]:
        return {"PGHOST": "127.0.0.1", "DATABASE_URL": self.url}


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    FakeRootd.calls = []
    FakeRootd.fail_on = set()
    FakeRootd.listed_rules = []
    monkeypatch.setattr(expose, "LocalRootdClient", FakeRootd)
    monkeypatch.setattr(expose, "get_addon", lambda t, n: _Addon(PG_URL))


def _narrow_range(monkeypatch, low: int, high: int) -> None:
    monkeypatch.setattr(expose, "PORT_RANGE_LOW", low)
    monkeypatch.setattr(expose, "PORT_RANGE_HIGH", high)


def _free_port_pair() -> int:
    """A port P such that P and P+1 are both free right now."""
    for _ in range(50):
        with socket.socket() as probe:
            probe.bind(("0.0.0.0", 0))
            port = probe.getsockname()[1]
        if expose._port_is_free(port) and expose._port_is_free(port + 1):
            return port
    pytest.fail("no two adjacent free ports found")


# --- pure helpers ---------------------------------------------------------


def test_connection_url_picks_url_key():
    assert connection_url({"PGHOST": "x", "DATABASE_URL": PG_URL}) == PG_URL
    assert connection_url({"PGHOST": "x"}) is None


def test_rewrite_url_swaps_host_and_port_keeps_credentials():
    assert (
        _rewrite_url(PG_URL, "db.example.com", 54312)
        == "postgresql://u:secret@db.example.com:54312/mydb"
    )


# --- allocate_public_port -------------------------------------------------


def test_allocate_returns_a_free_in_range_port(repo):
    port = allocate_public_port(repo)
    assert expose.PORT_RANGE_LOW <= port <= expose.PORT_RANGE_HIGH


def test_allocate_skips_claimed_port(repo, db_session, monkeypatch):
    low = _free_port_pair()
    _narrow_range(monkeypatch, low, low + 1)
    db_session.add(PortClaim(app_id=None, number=low, protocol="tcp", app_name="x"))
    db_session.flush()

    assert allocate_public_port(repo) == low + 1


def test_allocate_skips_socket_bound_port(repo, monkeypatch):
    low = _free_port_pair()
    _narrow_range(monkeypatch, low, low + 1)
    with socket.socket() as holder:
        holder.bind(("0.0.0.0", low))
        holder.listen()
        assert allocate_public_port(repo) == low + 1


def test_allocate_exhausted_aborts(repo, db_session, monkeypatch):
    _narrow_range(monkeypatch, 20000, 20001)
    db_session.add_all([
        PortClaim(app_id=None, number=20000, protocol="tcp", app_name="a"),
        PortClaim(app_id=None, number=20001, protocol="tcp", app_name="b"),
    ])
    db_session.flush()

    with pytest.raises(Abort, match="no free port"):
        allocate_public_port(repo)


# --- expose_addon ---------------------------------------------------------


def test_expose_happy_path_opens_firewall_and_proxy(repo, db_session):
    result = expose_addon(
        "postgres", "mydb", source="any", host="db.example.com", db_session=db_session
    )

    ops = [op for op, _ in FakeRootd.calls]
    assert ops == ["firewall.add_rule", "proxy.add"]  # firewall first, then proxy
    assert FakeRootd.calls[1][1]["target_port"] == 5432
    port = result["public_port"]
    assert result["url"] == f"postgresql://u:secret@db.example.com:{port}/mydb"
    assert result["already_exposed"] is False
    claim = repo.find_by_addon("postgres", "mydb")
    assert claim is not None
    assert (claim.number, claim.rule_id, claim.proxy_unit) == (port, "r1", "u1")


def test_expose_is_idempotent_when_already_exposed(db_session):
    db_session.add(
        PortClaim(
            app_id=None,
            number=9999,
            protocol="tcp",
            app_name="expose-postgres-mydb",
            addon_type="postgres",
            addon_name="mydb",
            source="10.0.0.0/8",
        )
    )
    db_session.flush()

    result = expose_addon(
        "postgres", "mydb", source="any", host="db.example.com", db_session=db_session
    )

    assert FakeRootd.calls == []  # no second port, no firewall change
    assert result["already_exposed"] is True
    assert result["public_port"] == 9999
    assert result["source"] == "10.0.0.0/8"
    assert result["url"].endswith("@db.example.com:9999/mydb")


def test_expose_rolls_back_firewall_and_claim_when_proxy_fails(repo, db_session):
    FakeRootd.fail_on = {"proxy.add"}

    with pytest.raises(Abort, match=r"proxy\.add boom"):
        expose_addon("postgres", "mydb", source="any", host="h", db_session=db_session)

    # The opened firewall rule is removed, and no claim row survives.
    assert ("firewall.remove_rule", {"rule_id": "r1"}) in FakeRootd.calls
    assert repo.find_by_addon("postgres", "mydb") is None


def test_expose_rollback_names_a_rule_it_could_not_close(repo, db_session):
    """The rollback swallowed its own failure and claimed a full rollback."""
    FakeRootd.fail_on = {"proxy.add", "firewall.remove_rule"}

    with pytest.raises(Abort, match=r"rule r1 is still open") as exc:
        expose_addon("postgres", "mydb", source="any", host="h", db_session=db_session)
    assert "was rolled back" not in str(exc.value)


def test_a_port_taken_meanwhile_is_reported_as_a_race(db_session, monkeypatch):
    # Another operation committed the port between allocation and our flush.
    db_session.add(PortClaim(app_id=None, number=54312, protocol="tcp", app_name="x"))
    db_session.commit()
    monkeypatch.setattr(expose, "allocate_public_port", lambda repo: 54312)

    with pytest.raises(Abort, match="concurrent operation"):
        expose_addon("postgres", "mydb", source="any", host="h", db_session=db_session)


def test_any_other_constraint_surfaces_as_itself(db_session, monkeypatch):
    """A migrated SQLite port_claim could not assign ids: it read as a race."""
    monkeypatch.setattr(expose, "allocate_public_port", lambda repo: None)

    with pytest.raises(IntegrityError, match=r"port_claim\.number"):
        expose_addon("postgres", "mydb", source="any", host="h", db_session=db_session)


# --- unexpose_addon -------------------------------------------------------


def test_unexpose_noop_when_not_exposed(db_session):
    assert unexpose_addon("postgres", "mydb", db_session=db_session) is None
    assert FakeRootd.calls == []


def test_unexpose_drops_claim_and_tears_down_rootd(repo, db_session):
    db_session.add(
        PortClaim(
            app_id=None,
            number=20001,
            protocol="tcp",
            app_name="expose-postgres-mydb",
            addon_type="postgres",
            addon_name="mydb",
            rule_id="r1",
            proxy_unit="u1",
        )
    )
    db_session.flush()
    FakeRootd.listed_rules = [{"rule_id": "r2"}]

    assert unexpose_addon("postgres", "mydb", db_session=db_session) == []

    assert repo.find_by_addon("postgres", "mydb") is None
    ops = [op for op, _ in FakeRootd.calls]
    assert "proxy.remove" in ops
    # Both the stored rule and the swept rule are removed.
    removed = {
        a["rule_id"] for op, a in FakeRootd.calls if op == "firewall.remove_rule"
    }
    assert removed == {"r1", "r2"}


def test_unexpose_returns_what_rootd_could_not_remove(repo, db_session):
    """Every rootd failure here used to be suppressed: unexpose reported success."""
    db_session.add(
        PortClaim(
            app_id=None,
            number=20001,
            protocol="tcp",
            app_name="expose-postgres-mydb",
            addon_type="postgres",
            addon_name="mydb",
            rule_id="r1",
        )
    )
    db_session.flush()
    FakeRootd.fail_on = {"firewall.remove_rule", "proxy.remove"}

    leftovers = unexpose_addon("postgres", "mydb", db_session=db_session)

    assert leftovers == [
        "firewall rule r1 (firewall.remove_rule boom)",
        "forwarder of 'mydb' (proxy.remove boom)",
    ]
    assert repo.find_by_addon("postgres", "mydb") is None  # port freed anyway
