# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Run-detail controller: a run's results + the diff vs the previous run."""

from __future__ import annotations

import markdown
from dishka import FromDishka  # noqa: TC002 -- runtime: @inject resolves the annotation
from dishka.integrations.litestar import inject
from litestar import Controller, get
from litestar.exceptions import NotFoundException
from litestar.params import (
    FromPath,  # noqa: TC002 -- runtime: Litestar resolves the path-param annotation
)
from litestar.response import Template

from hop3_testlab.catalog import title_map
from hop3_testlab.discriminators import short_app, variant_of
from hop3_testlab.reports import build_run_report_md
from hop3_testlab.repositories import (
    RunsRepository,  # noqa: TC001 -- runtime: @inject resolves it
)
from hop3_testlab.trends import diff_results, suite_rollup
from hop3_testlab.web.guards import auth_guard

# Markdown extensions for rendering the narrative report (code fences, tables,
# and lists that don't need a blank line before them).
_MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists"]


def _result_row(r, titles: dict[str, str] | None = None) -> dict:
    """Flatten a result ORM row to a template/report dict (session must be open).

    ``titles`` maps a test's catalog name to its human title; falls back to the
    path leaf when a test isn't in the current catalog (renamed/removed).
    """
    titles = titles or {}
    return {
        "id": r.id,
        "test_name": r.test_name,
        "app": short_app(r.test_name),
        "title": titles.get(r.test_name) or short_app(r.test_name),
        "variant": variant_of(r.test_name),
        "category": r.category,
        "priority": r.priority,
        "passed": bool(r.passed),
        "status": r.status or ("pass" if r.passed else "fail"),
        "classification": r.classification,
        "headline": r.headline,
        "duration": r.duration,
        "error": r.error,
        "bundle_run_id": r.bundle_run_id,
    }


def _run_row(run) -> dict:
    """Flatten a run ORM row to a template/report dict (session must be open)."""
    return {
        "run_uid": run.run_uid,
        "mode": run.mode,
        "trigger": run.trigger,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "total": run.total_tests,
        "passed": run.passed_tests,
        "failed": run.failed_tests,
        "duration": run.duration,
        # Session metadata (progressive disclosure): named fields + the bag.
        "hop3_version": run.hop3_version,
        "git_sha": run.git_sha,
        "target_type": run.target_type,
        "target_name": run.target_name,
        "metadata": run.run_metadata or {},
    }


class RunsController(Controller):
    """One run: its test results (failed-first) and the regressions diff."""

    path = "/runs"
    guards = [auth_guard]  # noqa: RUF012

    @get("/{run_uid:str}")
    @inject
    async def detail(
        self, run_uid: FromPath[str], runs: FromDishka[RunsRepository]
    ) -> Template:
        run = runs.get(run_uid)
        if run is None:
            msg = f"No run {run_uid!r}"
            raise NotFoundException(msg)

        results = runs.results_for(run)
        previous = runs.previous_run(run)
        diff = diff_results(results, runs.results_for(previous) if previous else [])

        # Convert to dicts while the session is open (no detached ORM in templates).
        titles = title_map()
        result_rows = [_result_row(r, titles) for r in results]
        run_row = _run_row(run)
        report_md = build_run_report_md(run_row, result_rows, diff)
        report_html = markdown.markdown(report_md, extensions=_MD_EXTENSIONS)
        return Template(
            template_name="runs/detail.html",
            context={
                "title": f"Run {run.run_uid}",
                "run": run_row,
                "results": result_rows,
                "diff": diff,
                "rollup": suite_rollup(results),
                "previous_uid": previous.run_uid if previous else None,
                # "bad recipes" that unexpectedly passed — worth promoting.
                "xpass_count": sum(1 for r in results if r.status == "xpass"),
                # Narrative report (actionable failure summary) + its markdown source.
                "report_html": report_html,
                "report_md": report_md,
            },
        )

    @get("/{run_uid:str}/report.md", media_type="text/markdown")
    @inject
    async def report_markdown(
        self, run_uid: FromPath[str], runs: FromDishka[RunsRepository]
    ) -> str:
        """The narrative report as raw markdown — a shareable / exportable URL."""
        run = runs.get(run_uid)
        if run is None:
            msg = f"No run {run_uid!r}"
            raise NotFoundException(msg)
        results = runs.results_for(run)
        previous = runs.previous_run(run)
        diff = diff_results(results, runs.results_for(previous) if previous else [])
        return build_run_report_md(
            _run_row(run), [_result_row(r) for r in results], diff
        )
