# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Run-detail controller: a run's results + the diff vs the previous run."""

from __future__ import annotations

import subprocess
from typing import Annotated

import markdown
from dishka import FromDishka  # noqa: TC002 -- runtime: @inject resolves the annotation
from dishka.integrations.litestar import inject
from litestar import Controller, get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import (
    Body,
    FromPath,
)
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3_testlab.cloud_config import load_schedule
from hop3_testlab.discriminators import short_app, variant_of
from hop3_testlab.reports import build_run_report_md
from hop3_testlab.repositories import (
    RunsRepository,  # noqa: TC001 -- runtime: @inject resolves it
)
from hop3_testlab.trends import diff_results, suite_rollup
from hop3_testlab.web.guards import auth_guard

_FORM = Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)]

# Markdown extensions for rendering the narrative report (code fences, tables,
# and lists that don't need a blank line before them).
_MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists"]


def _result_row(r) -> dict:
    """Flatten a result ORM row to a template/report dict (session must be open)."""
    return {
        "id": r.id,
        "test_name": r.test_name,
        "app": short_app(r.test_name),
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

    @post("/trigger")
    @inject
    async def trigger(self, data: _FORM, runs: FromDishka[RunsRepository]) -> Redirect:
        """Kick off a run in the background: full suite, or a per-app build.

        Spawns a detached `hop3-testlab run` (the same path the scheduler uses);
        the run lease prevents colliding with an in-flight run.
        """
        target = (data.get("target") or "").strip() or load_schedule().target
        app = (data.get("app") or "").strip()
        mode = (data.get("mode") or "ci").strip()

        if runs.target_busy(target):
            return Redirect(path="/?run=busy", status_code=HTTP_303_SEE_OTHER)

        cmd = ["hop3-testlab", "run", "--target", target, "--trigger", "manual"]
        cmd += ["--apps", app] if app else ["--mode", mode]
        try:
            # Detached so it outlives the request; results land in the store.
            # Popen is fire-and-forget (returns at once), so it doesn't block the
            # event loop; argv is fixed (no shell) and the route is admin-only.
            subprocess.Popen(  # noqa: ASYNC220
                cmd,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return Redirect(path="/?run=error", status_code=HTTP_303_SEE_OTHER)
        return Redirect(path="/?run=started", status_code=HTTP_303_SEE_OTHER)

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
        result_rows = [_result_row(r) for r in results]
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
