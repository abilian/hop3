# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The build dispatcher: assign queued builds to free pool servers.

You never pick a server — this does (v2 spec §3/§6). Each tick it takes the
oldest pending ``BuildRequest``, finds an enabled pool server whose lease is
free, and runs that request's profile there. **Serial v1** — one running build at
a time (the scheduler runs this with ``max_instances=1`` and the run blocks);
parallel dispatch across the pool arrives with Postgres. A request that can't run
is marked ``failed`` with the reason — never silently dropped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hop3_testlab import leasing
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.models import DONE, FAILED, QUEUED, RUNNING
from hop3_testlab.repositories import (
    BuildQueueRepository,
    ProfilesRepository,
    RunsRepository,
    ServersRepository,
)
from hop3_testlab.sources import Source
from hop3_testlab.worker import EngineExitError, RunSpec, run_blockers, run_once

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session, sessionmaker

    from hop3_testlab.models import Server

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Claim:
    """A dispatched build: which request, which server, and what to run."""

    request_id: int
    target_id: str
    spec: RunSpec
    actor: str | None = None


def _kind_from_actor(actor: str | None) -> str:
    """
    The run's trigger kind for the dashboard, from the request's actor: the
    web button, the nightly cron, or an API caller. Unknown/absent → 'manual'.
    """
    return {"nightly": "scheduled", "web": "web"}.get(actor or "", actor or "manual")


def _free_server(session: Session) -> Server | None:
    """An enabled pool server whose lease is free, or None (all busy / none)."""
    runs = RunsRepository(session)
    for server in ServersRepository(session).list_all(enabled_only=True):
        if not runs.target_busy(server.target_id):
            return server
    return None


def _claim(factory: sessionmaker) -> _Claim | bool:
    """
    Claim the next runnable build: mark it running and return its inputs.

    Returns a :class:`_Claim` to run, ``True`` when it *acted* without running (a
    doomed request marked ``failed``), or ``False`` when there's nothing to do
    (empty queue, or no free server right now — the request stays pending).
    """
    session = factory()
    try:
        queue = BuildQueueRepository(session)
        request = queue.next_pending()
        if request is None:
            return False  # nothing queued
        profile = ProfilesRepository(session).get(request.profile_id)
        if profile is None:
            queue.mark(request.id, FAILED, detail="profile was deleted")
            session.commit()
            return True
        server = _free_server(session)
        if server is None:
            return False  # all pool servers busy / none enabled — leave pending
        blocker = run_blockers(server.target_id, None)
        if blocker:
            queue.mark(
                request.id, FAILED, server_target_id=server.target_id, detail=blocker
            )
            session.commit()
            logger.error(
                "Build %d refused on %s — %s", request.id, server.name, blocker
            )
            return True
        queue.mark(request.id, RUNNING, server_target_id=server.target_id)
        session.commit()
        return _Claim(
            request_id=request.id,
            target_id=server.target_id,
            actor=request.actor,
            spec=RunSpec(
                source=Source(profile.source_name, profile.source_url),
                source_ref=profile.source_ref,
                platform_ref=profile.platform_ref,
                selection=dict(profile.selection or {}),
                # A queued/nightly build is a clean, reproducible run: rebuild the
                # box first (the canonical path the `not apps` heuristic used to
                # silently skip — review #2/#7).
                blank_slate=True,
            ),
        )
    finally:
        session.close()


def _run_claim(
    factory: sessionmaker,
    claim: _Claim,
    executor: Callable[..., None] | None,
) -> tuple[str, str | None]:
    """Run a claimed build (blocking). Returns its ``(status, detail)`` outcome."""
    try:
        ran = run_once(
            claim.target_id,
            trigger=f"build-{claim.request_id}",
            trigger_kind=_kind_from_actor(claim.actor),
            spec=claim.spec,
            executor=executor,
        )
    except EngineExitError as e:
        # The engine ran but exited non-zero. That's either a completed run with
        # failing tests (results recorded — the normal red build) or a genuine
        # crash before any result was recorded. Both stay FAILED, but only the
        # latter is a "crash"; tell them apart from the run the engine produced.
        return _classify_engine_exit(factory, claim, e)
    except Exception as e:  # the run crashed — surface the reason, don't drop it
        logger.exception("Build %d crashed on %s", claim.request_id, claim.target_id)
        return FAILED, str(e)
    if not ran:
        # Lost the lease in the claim→run window (another process grabbed the
        # target). It's not a failure — requeue so the next tick retries it.
        return QUEUED, None
    return DONE, None


# BuildRequest.detail is now Text, so this is just a sanity backstop against a
# pathological dump — generous enough that a real deploy/crash summary (the
# engine's ~25-line failure tail) is stored whole instead of truncated mid-error.
# The full output always lives in the engine log the detail points to.
_DETAIL_MAX = 6000


def _classify_engine_exit(
    factory: sessionmaker, claim: _Claim, exc: EngineExitError
) -> tuple[str, str | None]:
    """
    Distinguish a completed-with-failures run from a genuine engine crash.

    A completed run records a :class:`TestRun` with per-test results *before* the
    engine exits 1, so its presence is the discriminator. When results exist we
    log a plain "completed with N failures" (no traceback) and surface the
    failing test names — the actionable signal the operator wants — instead of
    mislabelling the routine red build as a crash. With no recorded results the
    engine died in setup/deploy/blank-slate: that *is* a crash, logged loudly
    with the engine log path. Either way the build stays FAILED.
    """
    session = factory()
    try:
        runs = RunsRepository(session)
        run = runs.latest_by_trigger(f"build-{claim.request_id}")
        results = runs.results_for(run) if run is not None else []
    finally:
        session.close()

    if run is not None and results:
        failed = [r.test_name for r in results if not r.passed]
        logger.warning(
            "Build %d completed on %s: %d/%d test(s) failed",
            claim.request_id,
            claim.target_id,
            len(failed),
            len(results),
        )
        return FAILED, _failed_detail(failed, len(results))

    logger.error(
        "Build %d crashed on %s — engine exited %d before recording any result. See %s",
        claim.request_id,
        claim.target_id,
        exc.returncode,
        exc.log_path,
    )
    return FAILED, str(exc)


def _failed_detail(failed: list[str], total: int) -> str:
    """A concise, actionable build detail: how many failed and which ones."""
    detail = f"{len(failed)} of {total} test(s) failed: {', '.join(failed)}"
    if len(detail) <= _DETAIL_MAX:
        return detail
    return detail[: _DETAIL_MAX - 1] + "…"


def _cap_detail(detail: str | None) -> str | None:
    """
    Bound a detail to the column width so recording an outcome can never
    overflow ``BuildRequest.detail`` (varchar 500).

    A crash detail (the engine-log tail) once exceeded it and threw
    ``StringDataRightTruncation`` *inside* ``_record`` — killing the dispatch
    thread, leaving the build wedged, which the orphan sweep then mislabelled as
    "dispatcher restarted while running". The full text lives in the engine log
    the detail points to, so truncating the stored summary loses nothing.
    """
    if detail is None or len(detail) <= _DETAIL_MAX:
        return detail
    return detail[: _DETAIL_MAX - 1] + "…"


def _record(
    factory: sessionmaker, request_id: int, status: str, detail: str | None
) -> None:
    """Stamp the build's outcome (its own short session)."""
    session = factory()
    try:
        # Cap centrally: every outcome write goes through here, so no caller (the
        # crash path returns an uncapped str(exc)) can overflow the detail column.
        fields: dict = {"detail": _cap_detail(detail)}
        if status == QUEUED:
            fields["server_target_id"] = None  # release it for the next pick
        else:
            # Link the build to the run it produced (resolved by its trigger tag).
            run = RunsRepository(session).latest_by_trigger(f"build-{request_id}")
            if run is not None:
                fields["run_uid"] = run.run_uid
        BuildQueueRepository(session).mark(request_id, status, **fields)
        session.commit()
    finally:
        session.close()


def _sweep_stale_running(factory: sessionmaker) -> None:
    """
    Fail builds left ``running`` by a dispatcher that died mid-run.

    A genuinely in-flight build still holds its target's lease; one whose lease is
    gone is stale (the dispatcher crashed before recording its outcome), so it'd
    sit ``running`` forever. Mark it failed so the queue tells the truth.
    """
    session = factory()
    try:
        queue = BuildQueueRepository(session)
        stale = [
            r
            for r in queue.list_running()
            if r.server_target_id and not leasing.is_held(session, r.server_target_id)
        ]
        for r in stale:
            queue.mark(
                r.id,
                FAILED,
                detail="dispatcher restarted while running; outcome unknown",
            )
            logger.error("Build %d stuck running (lease gone) — marked failed", r.id)
        if stale:
            session.commit()
    finally:
        session.close()


def dispatch_once(executor: Callable[..., None] | None = None) -> bool:
    """
    Dispatch at most one queued build to a free server.

    Returns True if it acted on a request (ran/failed/requeued it), False if there
    was nothing to do. ``executor`` is a test seam passed to ``run_once``.
    """
    factory = get_session_factory(TestlabConfig.get_instance().STORE_TARGET)
    _sweep_stale_running(factory)
    claim = _claim(factory)
    if isinstance(claim, bool):
        return claim
    status, detail = _run_claim(factory, claim, executor)  # blocks; lease serialises
    _record(factory, claim.request_id, status, detail)
    return True
