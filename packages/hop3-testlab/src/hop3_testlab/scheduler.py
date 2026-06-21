# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""In-process nightly scheduler (ADR 044 §10).

A cron job (default 00:00 local time) runs the suite via the worker, tagged
``scheduled-nightly``. It embeds in the web server (BackgroundScheduler, started
on app startup when ``[schedule].enabled``), or runs standalone via
``hop3-testlab schedule`` (BlockingScheduler). The worker's lease keeps a manual
run and the nightly from colliding.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.triggers.cron import CronTrigger

from hop3_testlab.cloud_config import load_schedule
from hop3_testlab.worker import run_blockers, run_once

if TYPE_CHECKING:
    from apscheduler.schedulers.base import BaseScheduler

logger = logging.getLogger(__name__)

NIGHTLY_JOB_ID = "nightly"
DISPATCH_JOB_ID = "dispatch"
DISPATCH_INTERVAL_SECONDS = 10


def _nightly_job() -> None:
    """Run the nightly suite. Config is read at fire time, so edits take effect.

    Pre-flights like the web trigger: a doomed run (an unauthorized Hetzner token,
    an unreachable box) is refused with the real reason and logged, rather than
    crashing deep in the executor as an unhandled scheduler traceback.
    """
    schedule = load_schedule()
    blocker = run_blockers(schedule.target, None)
    if blocker:
        logger.error("Nightly run refused — %s", blocker)
        return
    if not run_once(schedule.target, trigger="scheduled-nightly", mode=schedule.mode):
        logger.warning("Nightly run skipped — target %r is busy.", schedule.target)


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
    """Run the nightly scheduler in the foreground (the `schedule` command)."""
    from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: PLC0415

    add_nightly_job(BlockingScheduler()).start()
