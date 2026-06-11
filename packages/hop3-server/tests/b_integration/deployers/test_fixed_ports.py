# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Fixed-port registry: claim, conflict refusal, idempotent redeploy, firewall.

Uses a real in-memory DB (so the PortClaim table + unique constraint are
exercised) and a fake rootd client (so firewall open/close is verified without a
running daemon). This is the robustness guarantee: a second app claiming a port
another app holds is refused up front, and teardown frees it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from hop3.deployers.fixed_ports import (
    claim_fixed_ports,
    open_fixed_ports,
    release_fixed_ports,
)
from hop3.lib import Abort
from hop3.lib.rootd import RootdUnavailableError
from hop3.orm import App, PortClaimRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _cfg(*ports: tuple[int, str]):
    """A stand-in AppConfig exposing only ``.ports``."""
    return cast(
        "object",
        SimpleNamespace(
            ports=[{"number": n, "protocol": p, "name": None} for n, p in ports]
        ),
    )


def _app(session: Session, name: str) -> App:
    app = App(name=name)
    session.add(app)
    session.flush()  # assign app.id
    return app


class _FakeRootd:
    """Context-manager rootd client recording add/remove calls."""

    added: list[int] = []  # noqa: RUF012
    removed: list[str] = []  # noqa: RUF012

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def call(self, op: str, args: dict):
        if op == "firewall.add_rule":
            _FakeRootd.added.append(args["port"])
            return {"rule_id": "rule-xyz"}
        if op == "firewall.remove_rule":
            _FakeRootd.removed.append(args["rule_id"])
            return {"removed": True}
        if op == "firewall.list_rules":
            return {"rules": []}
        return {}


def test_claim_records_port(db_session: Session):
    app = _app(db_session, "owncast-1")
    claim_fixed_ports(app, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    claim = PortClaimRepository(session=db_session).find_active(1935, "tcp")
    assert claim is not None
    assert claim.app_id == app.id


def test_second_app_same_port_is_refused(db_session: Session):
    a1 = _app(db_session, "owncast-1")
    claim_fixed_ports(a1, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    a2 = _app(db_session, "owncast-2")
    with pytest.raises(Abort) as exc:
        claim_fixed_ports(a2, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    message = str(exc.value)
    assert "1935/tcp" in message
    assert "owncast-1" in message  # names the holder


def test_redeploy_same_app_is_idempotent(db_session: Session):
    app = _app(db_session, "owncast-1")
    claim_fixed_ports(app, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    claim_fixed_ports(app, _cfg((1935, "tcp")), db_session)  # again: must not raise  # type: ignore[arg-type]
    claims = PortClaimRepository(session=db_session).get_by_app_id(app.id)
    assert len(claims) == 1


def test_distinct_ports_coexist(db_session: Session):
    a1 = _app(db_session, "mail-1")
    claim_fixed_ports(a1, _cfg((25, "tcp")), db_session)  # type: ignore[arg-type]
    a2 = _app(db_session, "xmpp-1")
    claim_fixed_ports(a2, _cfg((5222, "tcp")), db_session)  # no conflict  # type: ignore[arg-type]
    repo = PortClaimRepository(session=db_session)
    c25 = repo.find_active(25, "tcp")
    c5222 = repo.find_active(5222, "tcp")
    assert c25 is not None
    assert c25.app_id == a1.id
    assert c5222 is not None
    assert c5222.app_id == a2.id


def test_open_then_release_firewall(db_session: Session, monkeypatch):
    _FakeRootd.removed = []
    app = _app(db_session, "owncast-1")
    claim_fixed_ports(app, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    monkeypatch.setattr("hop3.deployers.fixed_ports.LocalRootdClient", _FakeRootd)

    open_fixed_ports(app, db_session)
    repo = PortClaimRepository(session=db_session)
    claim = repo.find_active(1935, "tcp")
    assert claim is not None
    assert claim.rule_id == "rule-xyz"

    release_fixed_ports(app, db_session)
    assert _FakeRootd.removed == ["rule-xyz"]
    # Release frees the registry row too, not just the firewall.
    assert repo.find_active(1935, "tcp") is None


def test_release_frees_port_for_reuse_without_app_delete(db_session: Session):
    # Regression for the owncast 1935 leak: releasing fixed ports must free the
    # registry even when the App row is never deleted (e.g. filesystem/Docker
    # cleanup failed mid-destroy). Otherwise the claim is stranded and blocks
    # every future deploy of that port.
    app = _app(db_session, "owncast-1")
    claim_fixed_ports(app, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    repo = PortClaimRepository(session=db_session)
    assert repo.find_active(1935, "tcp") is not None

    release_fixed_ports(app, db_session)  # App row intentionally NOT deleted
    assert repo.find_active(1935, "tcp") is None

    other = _app(db_session, "owncast-2")
    claim_fixed_ports(other, _cfg((1935, "tcp")), db_session)  # must succeed  # type: ignore[arg-type]
    freed = repo.find_active(1935, "tcp")
    assert freed is not None
    assert freed.app_id == other.id


def test_open_degrades_when_rootd_unavailable(db_session: Session, monkeypatch):
    app = _app(db_session, "owncast-1")
    claim_fixed_ports(app, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]

    class _Down:
        def __enter__(self):
            raise RootdUnavailableError

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("hop3.deployers.fixed_ports.LocalRootdClient", _Down)
    open_fixed_ports(app, db_session)  # must NOT raise — claim stands, port unopened
    claim = PortClaimRepository(session=db_session).find_active(1935, "tcp")
    assert claim is not None
    assert claim.rule_id is None


def test_removed_port_is_reconciled(db_session: Session):
    # Declaring 1935, then redeploying WITHOUT it, must release the stale claim
    # (otherwise it leaks and wrongly blocks another app — the inverse heisenbug).
    app = _app(db_session, "owncast-1")
    claim_fixed_ports(app, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    repo = PortClaimRepository(session=db_session)
    assert repo.find_active(1935, "tcp") is not None

    claim_fixed_ports(app, _cfg(), db_session)  # redeploy: no ports  # type: ignore[arg-type]
    assert repo.find_active(1935, "tcp") is None  # released

    other = _app(db_session, "rtmp-2")
    claim_fixed_ports(other, _cfg((1935, "tcp")), db_session)  # now free  # type: ignore[arg-type]
    freed = repo.find_active(1935, "tcp")
    assert freed is not None
    assert freed.app_id == other.id


def test_concurrent_race_aborts_cleanly(db_session: Session, monkeypatch):
    # Regression: when the find_active check misses but the unique constraint
    # catches the duplicate on flush, claim must roll back the poisoned flush and
    # re-read to name the holder — never surface the opaque "An invalid request
    # was made." that querying a poisoned session raises. Here find_active is
    # stubbed to always miss, so the holder can't be re-read and we fall back to
    # a generic name, but the abort is still clean.
    a = _app(db_session, "owncast-a")
    claim_fixed_ports(a, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    db_session.commit()  # a's claim is a committed holder the constraint enforces
    b = _app(db_session, "owncast-b")
    # Simulate the race: the pre-flight check sees nothing, so we fall through
    # to the insert, where the unique constraint fires.
    monkeypatch.setattr(
        PortClaimRepository, "find_active", lambda self, n, p="tcp": None
    )
    with pytest.raises(Abort) as exc:
        claim_fixed_ports(b, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    message = str(exc.value)
    assert "1935/tcp" in message
    assert "invalid request" not in message.lower()


def test_race_names_the_real_holder(db_session: Session, monkeypatch):
    # When the pre-flight check misses but the constraint catches the duplicate,
    # the abort must still name the *actual* holder (re-read on a fresh snapshot
    # after rolling back the failed flush) — not the generic "another app" the
    # user saw. Reproduces the reported owncast 1935/tcp diagnosis gap.
    a = _app(db_session, "owncast-a")
    claim_fixed_ports(a, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    db_session.commit()  # a is a committed holder

    real_find = PortClaimRepository.find_active
    calls = {"n": 0}

    def flaky(self, n, p="tcp"):
        # Miss on the pre-flight check (call 1), then behave normally so the
        # post-rollback re-read returns the real holder.
        calls["n"] += 1
        return None if calls["n"] == 1 else real_find(self, n, p)

    monkeypatch.setattr(PortClaimRepository, "find_active", flaky)

    b = _app(db_session, "owncast-b")
    with pytest.raises(Abort) as exc:
        claim_fixed_ports(b, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    message = str(exc.value)
    assert "1935/tcp" in message
    assert "owncast-a" in message  # the real holder, not "another app"
    assert "another app" not in message


def test_docker_runtime_skips_firewall(db_session: Session, monkeypatch):
    _FakeRootd.added = []
    app = _app(db_session, "owncast-1")
    app.runtime = "docker-compose"  # Docker apps don't publish declared ports yet
    claim_fixed_ports(app, _cfg((1935, "tcp")), db_session)  # type: ignore[arg-type]
    monkeypatch.setattr("hop3.deployers.fixed_ports.LocalRootdClient", _FakeRootd)

    open_fixed_ports(app, db_session)
    assert _FakeRootd.added == []  # no firewall rule opened for a Docker app
    # ...but the claim still stands, so conflict detection applies host-wide
    assert PortClaimRepository(session=db_session).find_active(1935, "tcp") is not None
