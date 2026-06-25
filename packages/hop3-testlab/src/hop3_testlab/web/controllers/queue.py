# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The build queue — pending / running / done, and cancel a pending build.

Start-build enqueues a request (no target); the dispatcher assigns a free pool
server and runs it. A request that can't run is recorded ``failed`` with its
reason — surfaced here, not buried in a log (v2 spec §3).
"""

from __future__ import annotations

from dishka import FromDishka  # noqa: TC002 -- runtime: @inject resolves the annotation
from dishka.integrations.litestar import inject
from litestar import Controller, get, post
from litestar.params import (
    FromPath,  # noqa: TC002 -- runtime: Litestar resolves the path annotation
)
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3_testlab.config import TestlabConfig
from hop3_testlab.repositories import (  # noqa: TC001 -- runtime: @inject resolves them
    BuildQueueRepository,
    ProfilesRepository,
)
from hop3_testlab.web.guards import auth_guard

_LOG_MAX_BYTES = 200_000


def _build_log_text(request_id: int) -> str | None:
    """The engine run log for build N (the full ``hop3-test`` output), read from the
    app data dir (``DATA_DIR/logs/build-<id>-*.log``, newest match).

    Tail-capped so a huge log doesn't blow up the page; the file on disk keeps it
    all. Returns None when no log exists yet (pending/cancelled, or pre-move runs).
    """
    log_dir = TestlabConfig.get_instance().DATA_DIR / "logs"
    matches = sorted(log_dir.glob(f"build-{request_id}-*.log"))
    if not matches:
        return None
    text = matches[-1].read_text(encoding="utf-8", errors="replace")
    if len(text) > _LOG_MAX_BYTES:
        return "… (truncated; full log on the server) …\n" + text[-_LOG_MAX_BYTES:]
    return text


class QueueController(Controller):
    """The build queue + cancel."""

    path = "/queue"
    guards = [auth_guard]  # noqa: RUF012

    @get("/")
    @inject
    async def index(
        self,
        queue: FromDishka[BuildQueueRepository],
        profiles: FromDishka[ProfilesRepository],
    ) -> Template:
        names = {p.id: p.name for p in profiles.list_all()}
        builds = [
            {
                "id": r.id,
                "profile": names.get(r.profile_id, f"#{r.profile_id}"),
                "status": r.status,
                "server": r.server_target_id or "—",
                "detail": r.detail or "",
                "actor": r.actor or "",
                "created_at": r.created_at,
            }
            for r in queue.list_recent()
        ]
        return Template(
            template_name="queue/index.html",
            context={"title": "Queue", "builds": builds},
        )

    @get("/{request_id:int}/log")
    @inject
    async def log(
        self, request_id: FromPath[int], queue: FromDishka[BuildQueueRepository]
    ) -> Template:
        """The build's engine log, fetched from disk and shown in the UI — so a
        failure is readable here instead of a 'diagnostics saved to <path>' pointer."""
        build = queue.get(request_id)
        return Template(
            template_name="queue/log.html",
            context={
                "title": f"Build #{request_id} log",
                "request_id": request_id,
                "status": build.status if build else None,
                "log": _build_log_text(request_id),
            },
        )

    @post("/{request_id:int}/cancel")
    @inject
    async def cancel(
        self, request_id: FromPath[int], queue: FromDishka[BuildQueueRepository]
    ) -> Redirect:
        queue.cancel(request_id)  # a no-op once dispatched
        return Redirect(path="/queue", status_code=HTTP_303_SEE_OTHER)
