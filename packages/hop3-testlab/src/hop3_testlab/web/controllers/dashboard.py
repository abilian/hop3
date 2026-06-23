# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard + health controllers.

The dashboard handler demonstrates the decided DI pattern (spec §2/§9):
``@inject`` + ``FromDishka[...]`` rather than a manual ``get_session()``. It is
read-only: a run is started from a Profile (``/profiles`` → Start build → the
queue), never from here.
"""

from __future__ import annotations

from dishka import FromDishka  # noqa: TC002 -- runtime: @inject resolves the annotation
from dishka.integrations.litestar import inject
from litestar import Controller, get
from litestar.response import Template

from hop3_testlab.repositories import (
    RunsRepository,  # noqa: TC001 -- runtime: @inject resolves it
)
from hop3_testlab.web.guards import auth_guard


def _display_trigger(run) -> str:
    """The run's initiator kind (web / scheduled / cli) for the dashboard, from
    the recorded provenance. Legacy queue runs without a recorded kind show
    'queued' rather than the bare 'build-N' request id."""
    kind = (run.run_metadata or {}).get("trigger_kind")
    if kind:
        return kind
    trigger = run.trigger or ""
    if trigger.startswith("build-"):
        return "queued"
    return trigger or "—"


class HealthController(Controller):
    """Liveness probe — always public, no DI."""

    path = "/health"

    @get("/", sync_to_thread=False)
    def health(self) -> dict[str, str]:
        return {"status": "ok"}


class DashboardController(Controller):
    """The morning dashboard: recent runs (read-only)."""

    path = "/"
    guards = [auth_guard]  # noqa: RUF012

    @get("/")
    @inject
    async def index(self, runs: FromDishka[RunsRepository]) -> Template:
        # Convert to plain dicts here, while the session is open, so the template
        # never touches detached ORM objects (the hop3-server dashboard pattern).
        rows = [
            {
                "run_uid": run.run_uid,
                "mode": run.mode,
                "trigger": _display_trigger(run),
                "target": run.target_name or run.target_type,
                "started_at": run.started_at,
                "total": run.total_tests,
                "passed": run.passed_tests,
                "failed": run.failed_tests,
                "duration": run.duration,
                "ok": (run.failed_tests or 0) == 0,
                "finished": run.finished_at is not None,
                "aborted": bool((run.run_metadata or {}).get("aborted")),
            }
            for run in runs.list_recent(limit=20)
        ]
        return Template(
            template_name="dashboard/index.html",
            context={"title": "Hop3 Test Lab", "runs": rows},
        )
