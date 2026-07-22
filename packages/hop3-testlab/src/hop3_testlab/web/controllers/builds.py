# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Build detail: one build's metadata + full per-phase logs (ADR 044 §E)."""

from __future__ import annotations

from dishka import (
    FromDishka,  # ruff:ignore[typing-only-third-party-import] -- runtime: @inject resolves the annotation
)
from dishka.integrations.litestar import inject
from litestar import Controller, get
from litestar.exceptions import NotFoundException
from litestar.params import (
    FromPath,  # ruff:ignore[typing-only-third-party-import] -- runtime: Litestar resolves it
)
from litestar.response import Template

from hop3_testlab.catalog import title_map
from hop3_testlab.repositories import (
    RunsRepository,  # ruff:ignore[typing-only-first-party-import] -- runtime: @inject resolves it
)
from hop3_testlab.web.guards import auth_guard


class BuildController(Controller):
    """One build: status, per-phase timings, and full per-phase logs."""

    path = "/builds"
    guards = [auth_guard]  # ruff:ignore[mutable-class-default]

    @get("/{result_id:int}")
    @inject
    async def detail(
        self, result_id: FromPath[int], runs: FromDishka[RunsRepository]
    ) -> Template:
        record = runs.get_result(result_id)
        if record is None:
            msg = f"No build {result_id}"
            raise NotFoundException(msg)

        logs = runs.build_logs(result_id)
        human_title = title_map().get(record.test_name)
        return Template(
            template_name="builds/detail.html",
            context={
                "title": f"Build {human_title or record.test_name}",
                "test_name": record.test_name,
                "human_title": human_title,
                "status": record.status or ("pass" if record.passed else "fail"),
                "passed": record.passed,
                "classification": record.classification,
                "duration": record.duration,
                "timings": record.phase_timings or {},
                "logs": logs,  # [{phase, text, size}]
                "run_uid": record.run.run_uid if record.run else None,
            },
        )
