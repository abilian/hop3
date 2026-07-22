# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Bundle drill-down: the per-section diagnostic logs behind a failure."""

from __future__ import annotations

from pathlib import Path

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

from hop3_testlab.bundles import read_bundle_sections
from hop3_testlab.repositories import (
    RunsRepository,  # ruff:ignore[typing-only-first-party-import] -- runtime: @inject resolves it
)
from hop3_testlab.web.guards import auth_guard


class BundleController(Controller):
    """The diagnostic bundle for one failed test (build/app/nginx/journal/...)."""

    path = "/bundle"
    guards = [auth_guard]  # ruff:ignore[mutable-class-default]

    @get("/{bundle_run_id:str}")
    @inject
    async def view(
        self, bundle_run_id: FromPath[str], runs: FromDishka[RunsRepository]
    ) -> Template:
        record = runs.result_by_bundle(bundle_run_id)
        if record is None or not record.bundle_path:
            msg = f"No bundle {bundle_run_id!r}"
            raise NotFoundException(msg)

        sections = read_bundle_sections(Path(record.bundle_path))
        return Template(
            template_name="bundle/view.html",
            context={
                "title": f"Bundle {bundle_run_id}",
                "bundle_run_id": bundle_run_id,
                "test_name": record.test_name,
                "classification": record.classification,
                "headline": record.headline,
                "sections": sections,
            },
        )
