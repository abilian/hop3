# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Per-type (app/demo/tutorial) live progress for the running panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_testing.results import ResultStore
from hop3_testing.results.models import TestResultRecord, TestRun
from hop3_testlab.discriminators import type_of
from hop3_testlab.repositories import RunsRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from pathlib import Path


def test_type_of_classifies_paths():
    assert type_of("apps/real-apps-nix/edrix") == "app"
    assert type_of("demos/wordpress") == "demo"
    assert type_of("docs/src/tutorials/static/hugo.md") == "tutorial"
    assert type_of(None) == "app"


def test_progress_by_type_groups_results(tmp_path: Path):
    db = tmp_path / "r.db"
    ResultStore(db_path=db)  # ensure schema
    engine = create_engine(f"sqlite:///{db}")
    with Session(engine) as session:
        run = TestRun(
            run_uid="r1", mode="nightly", target_type="docker", target_name="t"
        )
        session.add(run)
        session.flush()
        rows = [
            ("apps/a", True),
            ("apps/b", False),
            ("demos/d", True),
            ("docs/src/tutorials/static/hugo.md", True),
            ("docs/src/tutorials/static/astro.md", False),
        ]
        session.add_all(
            TestResultRecord(run_id=run.id, test_name=n, passed=p) for n, p in rows
        )
        session.commit()
        prog = RunsRepository(session).progress_by_type(run)

    assert prog["app"] == {"done": 2, "passed": 1, "failed": 1}
    assert prog["demo"] == {"done": 1, "passed": 1, "failed": 0}
    assert prog["tutorial"] == {"done": 2, "passed": 1, "failed": 1}
