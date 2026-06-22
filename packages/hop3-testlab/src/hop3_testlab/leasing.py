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
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_testing.results.models import RunLease
from sqlalchemy import CursorResult, or_, update
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

DEFAULT_TTL_SECONDS = 6 * 3600  # the nightly budget; a run releases on finish


def proc_starttime(pid: int) -> int | None:
    """The process start-time (jiffies since boot, ``/proc/<pid>/stat`` field 22).

    A reuse-proof identity for the engine PID: the kernel never reissues the same
    (pid, starttime) pair. Returns None when unreadable (process gone, or no
    procfs — e.g. a macOS dev machine), in which case identity can't be checked.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    # comm (field 2) is parenthesised and may contain spaces/parens; index from
    # the last ')' so the remaining whitespace-split fields line up.
    rparen = stat.rfind(")")
    if rparen == -1:
        return None
    fields = stat[rparen + 2 :].split()
    try:
        return int(fields[19])  # field 22 overall; 20th after comm -> index 19
    except (IndexError, ValueError):
        return None


def _holder_alive(lease: RunLease) -> bool:
    """True if the lease's holder process is still running — so its run is live
    even past the TTL and must not be stolen. Best-effort: unverifiable without
    procfs (no pid, or a macOS dev box) -> treated as dead (TTL governs)."""
    if lease.pid is None or lease.pid_starttime is None:
        return False
    return proc_starttime(lease.pid) == lease.pid_starttime


def try_acquire(
    session: Session,
    target_id: str,
    holder: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> bool:
    """Acquire the lease for ``target_id``. Return False if a live one is held.

    Reclaim is gated on liveness, not just the TTL: a lease whose holder process
    is still alive is never stolen (a >TTL but healthy run keeps its target —
    otherwise a second run could start on the same box, #1). The conditional
    UPDATE still serialises racing reclaims of a genuinely dead holder (the SQLite
    write lock / Postgres row lock), and a brand-new lease is an INSERT guarded by
    the unique ``target_id`` constraint.
    """
    now = time.time()
    expires = now + ttl_seconds
    existing = (
        session.query(RunLease).filter(RunLease.target_id == target_id).one_or_none()
    )
    if existing is not None:
        live = bool(existing.expires_at) and existing.expires_at > now
        if live or _holder_alive(existing):
            session.rollback()
            return False  # held, or expired-but-engine-still-running (#1)

    result = session.execute(
        update(RunLease)
        .where(
            RunLease.target_id == target_id,
            or_(RunLease.expires_at.is_(None), RunLease.expires_at <= now),
        )
        # Clear the dead holder's PID so the new holder's set_pid starts clean.
        .values(
            holder=holder,
            acquired_at=now,
            expires_at=expires,
            pid=None,
            pid_starttime=None,
        )
        .execution_options(synchronize_session=False)
    )
    claimed = result.rowcount if isinstance(result, CursorResult) else 0
    if claimed:
        session.commit()
        return True

    # The UPDATE matched nothing: a live lease holds it (raced us), or there's no
    # row to reclaim — INSERT a fresh one.
    if existing is not None:
        session.rollback()
        return False  # another acquirer reclaimed it first
    try:
        session.add(
            RunLease(
                target_id=target_id,
                holder=holder,
                acquired_at=now,
                expires_at=expires,
            )
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        return False  # a concurrent acquirer inserted first
    return True


def others_live(session: Session, target_id: str) -> bool:
    """True if a live lease for *another* target is held (something else is running).

    Lets the orphan-sweep stay safe under concurrent runs (nightly vs dispatcher
    on different targets): only sweep when nothing else is live, so a healthy run
    on another target is never aborted.
    """
    now = time.time()
    return bool(
        session
        .query(RunLease)
        .filter(
            RunLease.target_id != target_id,
            RunLease.expires_at.isnot(None),
            RunLease.expires_at > now,
        )
        .count()
    )


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
