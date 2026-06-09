# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard + health controllers.

The dashboard handler demonstrates the decided DI pattern (spec §2/§9):
``@inject`` + ``FromDishka[...]`` rather than a manual ``get_session()``.
Auth (the ``auth_guard``) and the real run/test/trends views land in a later
milestone; for now the index is public and static.
"""

from __future__ import annotations

from dishka import FromDishka  # noqa: TC002 -- runtime: @inject resolves the annotation
from dishka.integrations.litestar import inject
from litestar import Controller, Request, get
from litestar.response import Template

from hop3_testlab.cloud_config import load_schedule
from hop3_testlab.repositories import (
    RunsRepository,  # noqa: TC001 -- runtime: @inject resolves it
)
from hop3_testlab.web.guards import auth_guard

_FLASH = {
    "started": ("ok", "Run started — refresh in a moment to see it appear."),
    "busy": ("warn", "A run is already in progress on that target."),
    "error": ("warn", "Couldn't start the run (is hop3-testlab on PATH?)."),
}


class HealthController(Controller):
    """Liveness probe — always public, no DI."""

    path = "/health"

    @get("/", sync_to_thread=False)
    def health(self) -> dict[str, str]:
        return {"status": "ok"}


class DashboardController(Controller):
    """The morning dashboard (placeholder until the query layer lands)."""

    path = "/"
    guards = [auth_guard]  # noqa: RUF012

    @get("/")
    @inject
    async def index(
        self, runs: FromDishka[RunsRepository], request: Request
    ) -> Template:
        # Convert to plain dicts here, while the session is open, so the template
        # never touches detached ORM objects (the hop3-server dashboard pattern).
        rows = [
            {
                "run_uid": run.run_uid,
                "mode": run.mode,
                "trigger": run.trigger,
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
        schedule = load_schedule()
        flash_key = str(request.query_params.get("run") or "")
        return Template(
            template_name="dashboard/index.html",
            context={
                "title": "Hop3 Test Lab",
                "runs": rows,
                "flash": _FLASH.get(flash_key),
                "modes": ["dev", "ci", "coverage", "nightly", "release"],
                "default_mode": schedule.mode,
                "default_target": schedule.target,
            },
        )
