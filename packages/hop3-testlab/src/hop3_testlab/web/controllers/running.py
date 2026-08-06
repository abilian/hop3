# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The live "current run" panel: visibility, ETA, and a stop control.

Rendered as an HTMX partial polled every few seconds from the dashboard, so an
in-flight run shows progress (tests done / expected, elapsed, ETA from history)
and can be stopped. "Running" is signalled by a held lease; the per-test detail
comes from the in-flight ``TestRun``.
"""

from __future__ import annotations

import time
from datetime import timezone
from typing import TYPE_CHECKING

from dishka import (
    FromDishka,  # ruff:ignore[typing-only-third-party-import] -- runtime: @inject resolves the annotation
)
from dishka.integrations.litestar import inject
from litestar import Controller, get, post
from litestar.response import Template

from hop3_testlab.repositories import (
    RunsRepository,  # ruff:ignore[typing-only-first-party-import] -- runtime: @inject resolves it
)
from hop3_testlab.trends import predict_progress
from hop3_testlab.web.guards import auth_guard
from hop3_testlab.worker import terminate_engine

if TYPE_CHECKING:
    from datetime import datetime

    from hop3_testing.results.models import TestRun


def _to_epoch(dt: datetime | None, fallback: float) -> float:
    """Epoch seconds for a (possibly tz-naive, SQLite-round-tripped) datetime."""
    if dt is None:
        return fallback
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _fmt_duration(seconds: float | None) -> str:
    """Human duration: '—', '45s', '4m 12s', '1h 03m'."""
    if seconds is None:
        return "—"
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m {total % 60:02d}s"
    return f"{total // 3600}h {(total % 3600) // 60:02d}m"


def _build_panel_context(runs: RunsRepository) -> dict:
    """Context for ``running/_panel.html`` — idle, starting, or running+ETA."""
    lease = runs.current_lease()
    if lease is None:
        return {"running": False}

    now = time.time()
    ctx: dict = {
        "running": True,
        "target": lease.target_id,
        "holder": lease.holder,
        "can_stop": bool(lease.pid),
    }

    active = runs.active_run()
    if active is None:
        # Lease taken, engine still warming up (no TestRun row yet).
        ctx["phase"] = "starting"
        return ctx

    history = runs.recent_completed(active.mode, active.target_type)
    prog = predict_progress(
        started_epoch=_to_epoch(active.started_at, now),
        now_epoch=now,
        done=active.total_tests or 0,
        history_durations=[r.duration for r in history if r.duration],
        history_totals=[r.total_tests for r in history if r.total_tests],
    )
    ctx.update({
        "phase": "running",
        "run_uid": active.run_uid,
        "mode": active.mode,
        "trigger": active.trigger,
        "done": prog["done"],
        "passed": active.passed_tests or 0,
        "failed": active.failed_tests or 0,
        "expected_total": prog["expected_total"],
        "progress_pct": prog["progress_pct"],
        "elapsed_text": _fmt_duration(prog["elapsed_seconds"]),
        "eta_text": _fmt_duration(prog["eta_seconds"]),
        "typical_text": _fmt_duration(prog["typical_seconds"]),
        "type_progress": _type_progress(runs, active),
    })
    return ctx


def _type_progress(runs: RunsRepository, active: TestRun) -> list[dict]:
    """
    Rows for the per-type progress table: done/planned + pass/fail per type.

    Planned counts come from the run (recorded by the engine at start); done
    counts from the results so far. The three types are always shown, in a
    stable order, even at zero.
    """
    planned = active.planned_counts or {}
    done = runs.progress_by_type(active)
    rows = []
    for key, label in (("app", "Apps"), ("demo", "Demos"), ("tutorial", "Tutorials")):
        d = done.get(key, {"done": 0, "passed": 0, "failed": 0})
        rows.append({
            "label": label,
            "planned": planned.get(key, 0),
            "done": d["done"],
            "passed": d["passed"],
            "failed": d["failed"],
        })
    return rows


class RunningController(Controller):
    """The live current-run panel (HTMX-polled) and its stop control."""

    path = "/running"
    guards = [auth_guard]  # ruff:ignore[mutable-class-default]

    @get("/")
    @inject
    async def panel(self, runs: FromDishka[RunsRepository]) -> Template:
        """Render the current-run panel (idle / starting / running)."""
        return Template(
            template_name="running/_panel.html",
            context=_build_panel_context(runs),
        )

    @post("/stop")
    @inject
    async def stop(self, runs: FromDishka[RunsRepository]) -> Template:
        """
        Stop the in-flight run: kill the engine group, mark it aborted, free
        the lease. Returns the refreshed (now idle) panel for HTMX to swap in.
        """
        lease = runs.current_lease()
        if lease is not None:
            # Read fields before the commits below expire the ORM object.
            pid, starttime, target_id = (
                lease.pid,
                lease.pid_starttime,
                lease.target_id,
            )
            if pid:
                terminate_engine(pid, starttime)
            runs.abort_active(by="web")
            runs.release_lease(target_id)
        return Template(
            template_name="running/_panel.html",
            context=_build_panel_context(runs),
        )
