# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""In-process scheduler (ADR 044 §10).

A cron job (default 00:00 local time) **enqueues** the configured build profile,
tagged ``nightly``; the dispatcher (an interval job) then runs it on a free pool
server — the same single path the UI's "Start build" uses. Both embed in the web
server (BackgroundScheduler, started on app startup when ``[schedule].enabled``),
or run standalone via ``hop3-testlab schedule`` (BlockingScheduler).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from apscheduler.triggers.cron import CronTrigger

from hop3_testlab.cloud_config import load_schedule
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import BuildQueueRepository, ProfilesRepository

if TYPE_CHECKING:
    from apscheduler.schedulers.base import BaseScheduler

logger = logging.getLogger(__name__)

NIGHTLY_JOB_ID = "nightly"
DISPATCH_JOB_ID = "dispatch"
DISPATCH_INTERVAL_SECONDS = 10

# The build currently running (serial v1). The 10s poll spawns the run on this
# thread and returns at once; while it's alive the poll is a no-op, so a build
# never blocks the scheduler thread — which would trip apscheduler's
# max_instances=1 and log "maximum instances reached" every tick for the whole
# (multi-hour) run.
_dispatch_thread: threading.Thread | None = None
_dispatch_lock = threading.Lock()


def _nightly_job() -> None:
    """Enqueue the nightly build. Config is read at fire time, so edits take effect.

    Enqueues the configured profile; the dispatcher picks a free pool server, runs
    it, and records failures as build rows (it pre-flights ``run_blockers`` there).
    Idle **loudly** when no profile is configured — never a silent no-op.
    """
    schedule = load_schedule()
    if not schedule.profile:
        logger.warning(
            "Nightly idle: no [schedule].profile configured — set it to a profile "
            "name (or TESTLAB_SCHEDULE_PROFILE) so the nightly has something to run."
        )
        return
    factory = get_session_factory(TestlabConfig.get_instance().STORE_TARGET)
    session = factory()
    try:
        profile = ProfilesRepository(session).by_name(schedule.profile)
        if profile is None:
            logger.error(
                "Nightly profile %r not found — create it or fix [schedule].profile.",
                schedule.profile,
            )
            return
        request = BuildQueueRepository(session).enqueue(profile.id, actor="nightly")
        session.commit()
        logger.info(
            "Nightly enqueued build %d for profile %r.", request.id, schedule.profile
        )
    finally:
        session.close()


def add_nightly_job(scheduler: BaseScheduler) -> BaseScheduler:
    """Register the nightly cron job (local time) on ``scheduler``."""
    schedule = load_schedule()
    scheduler.add_job(
        _nightly_job,
        CronTrigger(hour=schedule.hour, minute=schedule.minute),
        id=NIGHTLY_JOB_ID,
        replace_existing=True,
    )
    return scheduler


def _run_dispatch() -> None:
    """Worker-thread body: dispatch one queued build (claim → run → record). Runs
    off the scheduler thread so a multi-hour build doesn't block the 10s poll."""
    from hop3_testlab.dispatcher import (
        dispatch_once,
    )

    dispatch_once()


def _dispatch_job() -> None:
    """Poll: start one queued build on a dedicated worker thread and return at
    once (a no-op if a build is already running). Keeping the poll fast is what
    stops apscheduler's ``max_instances=1`` from skipping every tick — and logging
    a 'maximum instances reached' warning — for the whole duration of a run.

    The worker is a daemon: if the process is killed mid-build the run is
    abandoned, and the dispatcher's stale-RUNNING sweep + lease TTL recover it on
    the next start (the same path used when a dispatcher dies mid-run)."""
    global _dispatch_thread  # ruff:ignore[global-statement] — lock-guarded module singleton
    with _dispatch_lock:
        if _dispatch_thread is not None and _dispatch_thread.is_alive():
            return  # a build is already running — serial v1, nothing to do
        _dispatch_thread = threading.Thread(
            target=_run_dispatch, name="testlab-dispatch", daemon=True
        )
        _dispatch_thread.start()


def add_dispatch_job(scheduler: BaseScheduler) -> BaseScheduler:
    """Register the build-dispatch poll as a 10s interval job. The poll spawns the
    run on a worker thread and returns at once (``_dispatch_job``), so a long build
    never blocks it; ``max_instances=1`` stays as a belt-and-suspenders guard
    against overlapping polls — serial v1."""
    from apscheduler.triggers.interval import (
        IntervalTrigger,
    )

    scheduler.add_job(
        _dispatch_job,
        IntervalTrigger(seconds=DISPATCH_INTERVAL_SECONDS),
        id=DISPATCH_JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


def _quiet_apscheduler() -> None:
    """apscheduler logs every job execution at INFO, so the 10s dispatch poll
    prints two lines per tick forever. Lift its logger to WARNING — genuine
    misfires/errors still surface; the routine 'Running job … executed
    successfully' noise is dropped."""
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def build_background_scheduler(*, nightly: bool = True) -> BaseScheduler:
    """A BackgroundScheduler with the dispatch poll, ready to .start().

    The dispatch poll is **always** added so UI-triggered builds actually run; the
    nightly enqueue is added only when ``nightly`` (i.e. ``[schedule].enabled``).
    """
    from apscheduler.schedulers.background import (  # ruff:ignore[import-outside-top-level]
        BackgroundScheduler,
    )

    _quiet_apscheduler()
    scheduler = add_dispatch_job(BackgroundScheduler())
    if nightly:
        add_nightly_job(scheduler)
    return scheduler


def run_blocking() -> None:
    """Run the scheduler in the foreground (the `schedule` command): nightly cron +
    the build dispatcher, so enqueued builds actually run."""
    from apscheduler.schedulers.blocking import (
        BlockingScheduler,
    )

    _quiet_apscheduler()
    add_dispatch_job(add_nightly_job(BlockingScheduler())).start()
