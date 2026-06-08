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

from typing import TYPE_CHECKING

from apscheduler.triggers.cron import CronTrigger

from hop3_testlab.cloud_config import load_schedule
from hop3_testlab.worker import run_once

if TYPE_CHECKING:
    from apscheduler.schedulers.base import BaseScheduler

NIGHTLY_JOB_ID = "nightly"


def _nightly_job() -> None:
    """Run the nightly suite. Config is read at fire time, so edits take effect."""
    schedule = load_schedule()
    run_once(schedule.target, trigger="scheduled-nightly", mode=schedule.mode)


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


def build_background_scheduler() -> BaseScheduler:
    """A BackgroundScheduler with the nightly job, ready to .start() (for serve)."""
    from apscheduler.schedulers.background import (  # noqa: PLC0415
        BackgroundScheduler,
    )

    return add_nightly_job(BackgroundScheduler())


def run_blocking() -> None:
    """Run the nightly scheduler in the foreground (the `schedule` command)."""
    from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: PLC0415

    add_nightly_job(BlockingScheduler()).start()
