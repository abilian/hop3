# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Trends: flakiness ranking across recent runs (ADR 044 §E)."""

from __future__ import annotations

from dishka import FromDishka  # noqa: TC002 -- runtime: @inject resolves the annotation
from dishka.integrations.litestar import inject
from litestar import Controller, get
from litestar.response import Template

from hop3_testlab.repositories import (
    RunsRepository,  # noqa: TC001 -- runtime: @inject resolves it
)
from hop3_testlab.trends import flakiness_ranking
from hop3_testlab.web.guards import auth_guard


class TrendsController(Controller):
    """Cross-run trends (flakiness for now; pass-rate/duration to follow)."""

    path = "/trends"
    guards = [auth_guard]  # noqa: RUF012

    @get("/")
    @inject
    async def index(self, runs: FromDishka[RunsRepository]) -> Template:
        flaky = flakiness_ranking(runs.pass_fail_history(limit_runs=20))
        return Template(
            template_name="trends/index.html",
            context={"title": "Trends", "flaky": flaky},
        )
