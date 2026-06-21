# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Run lease: stop two runs from claiming the same target (ADR 044 §D).

A lock-row in the shared store, keyed by target id, with an epoch-seconds TTL so
a crashed holder's lease becomes reclaimable. This is the SQLite/v1 path; the
production path is a Postgres session advisory lock (auto-released on crash) —
see local-notes/specs/testlab-specs.md §11.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from hop3_testing.results.models import RunLease
from sqlalchemy import CursorResult, or_, update
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

DEFAULT_TTL_SECONDS = 6 * 3600  # the nightly budget; a run releases on finish


def try_acquire(
    session: Session,
    target_id: str,
    holder: str,
    *,
    run_uid: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> bool:
    """Acquire the lease for ``target_id``. Return False if a live one is held.

    Atomic, so two racing acquirers can't both claim the same target: a single
    conditional UPDATE claims an absent-or-expired lease (the SQLite write lock /
    Postgres row lock serialises the reclaim), and a brand-new lease is an INSERT
    guarded by the unique ``target_id`` constraint. The old read-check-write let
    two acquirers both reclaim one expired row.
    """
    now = time.time()
    expires = now + ttl_seconds
    result = session.execute(
        update(RunLease)
        .where(
            RunLease.target_id == target_id,
            or_(RunLease.expires_at.is_(None), RunLease.expires_at <= now),
        )
        .values(holder=holder, run_uid=run_uid, acquired_at=now, expires_at=expires)
        .execution_options(synchronize_session=False)
    )
    claimed = result.rowcount if isinstance(result, CursorResult) else 0
    if claimed:
        session.commit()
        return True

    # The UPDATE matched nothing: either a live lease holds it, or there's no row.
    if session.query(RunLease).filter(RunLease.target_id == target_id).count():
        session.rollback()
        return False  # a live lease is held
    try:
        session.add(
            RunLease(
                target_id=target_id,
                holder=holder,
                run_uid=run_uid,
                acquired_at=now,
                expires_at=expires,
            )
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        return False  # a concurrent acquirer inserted first
    return True


def is_held(session: Session, target_id: str) -> bool:
    """True if a live (unexpired) lease is held for ``target_id`` (UX check)."""
    now = time.time()
    lease = (
        session.query(RunLease).filter(RunLease.target_id == target_id).one_or_none()
    )
    return lease is not None and bool(lease.expires_at) and lease.expires_at > now


def set_pid(
    session: Session, target_id: str, pid: int, starttime: int | None = None
) -> None:
    """Record the engine PID (and its start-time) on the target's lease.

    ``starttime`` is the reuse-proof identity used by the stop control; None when
    it couldn't be read (e.g. no procfs).
    """
    lease = (
        session.query(RunLease).filter(RunLease.target_id == target_id).one_or_none()
    )
    if lease is not None:
        lease.pid = pid
        lease.pid_starttime = starttime
        session.commit()


def current_lease(session: Session) -> RunLease | None:
    """Return the live lease (newest, unexpired) across all targets, or None.

    The dashboard's "is something running" signal; there is normally at most one.
    """
    now = time.time()
    return (
        session
        .query(RunLease)
        .filter(RunLease.expires_at.isnot(None), RunLease.expires_at > now)
        .order_by(RunLease.acquired_at.desc())
        .first()
    )


def force_release(session: Session, target_id: str) -> None:
    """Delete the lease for ``target_id`` regardless of holder (stop path).

    Unlike :func:`release`, the caller (the web app) is not the lease holder.
    """
    lease = (
        session.query(RunLease).filter(RunLease.target_id == target_id).one_or_none()
    )
    if lease is not None:
        session.delete(lease)
        session.commit()


def release(session: Session, target_id: str, holder: str) -> None:
    """Release the lease iff this holder owns it (no-op otherwise)."""
    lease = (
        session
        .query(RunLease)
        .filter(RunLease.target_id == target_id, RunLease.holder == holder)
        .one_or_none()
    )
    if lease is not None:
        session.delete(lease)
        session.commit()
