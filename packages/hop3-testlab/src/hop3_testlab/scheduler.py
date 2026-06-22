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


def _dispatch_job() -> None:
    """Dispatch one queued build to a free pool server (no-op if nothing's ready)."""
    from hop3_testlab.dispatcher import dispatch_once  # noqa: PLC0415

    dispatch_once()


def add_dispatch_job(scheduler: BaseScheduler) -> BaseScheduler:
    """Register the build dispatcher as an interval job (``max_instances=1`` so a
    long-running build can't be double-dispatched — serial v1)."""
    from apscheduler.triggers.interval import IntervalTrigger  # noqa: PLC0415

    scheduler.add_job(
        _dispatch_job,
        IntervalTrigger(seconds=DISPATCH_INTERVAL_SECONDS),
        id=DISPATCH_JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


def build_background_scheduler() -> BaseScheduler:
    """A BackgroundScheduler with the nightly + dispatch jobs, ready to .start()."""
    from apscheduler.schedulers.background import (  # noqa: PLC0415
        BackgroundScheduler,
    )

    return add_dispatch_job(add_nightly_job(BackgroundScheduler()))


def run_blocking() -> None:
    """Run the scheduler in the foreground (the `schedule` command): nightly cron +
    the build dispatcher, so enqueued builds actually run."""
    from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: PLC0415

    add_dispatch_job(add_nightly_job(BlockingScheduler())).start()
