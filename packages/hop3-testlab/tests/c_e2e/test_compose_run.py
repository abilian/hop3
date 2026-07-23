# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
End-to-end: a composition run really deploys an app from source@ref on docker
and records it with the provenance stamp (v2 spec §A).

Establishes the c_e2e lane (real provision -> deploy -> collect). The directory
layer stamps it `e2e` + `needs_docker`; it also self-skips when docker isn't
usable. Unlike the isolated unit/integration layers, this shares the engine's
real store (~/.hop3/test-results.db): the spawned engine writes there and the Lab
reads it — exactly as in production.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from hop3_testing.targets.helpers import find_project_root
from hop3_testlab.config import TestlabConfig
from hop3_testlab.db import get_session_factory
from hop3_testlab.repositories import RunsRepository
from hop3_testlab.sources import Source
from hop3_testlab.worker import RunSpec, run_once

# Fastest real app (a static file server — no build, no addons).
STATIC_APP = "apps/test-apps-procfile/000-static"


def _docker_usable() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(["docker", "info"], capture_output=True, check=False)
    return probe.returncode == 0


# Opt-in: this does a real ~15-min platform deploy that is currently blocked by a
# hop3-installer/docker-env issue (the catalogue-baseline apt install in a
# no-systemd container) — see tasks/todo.md. Gated so normal `pytest` skips it;
# run on demand where the deploy works: `TESTLAB_E2E=1 pytest tests/c_e2e`.
pytestmark = pytest.mark.skipif(
    not (os.environ.get("TESTLAB_E2E") and _docker_usable()),
    reason="set TESTLAB_E2E=1 (with docker) to run the parked compose e2e",
)


def _current_branch(repo: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_compose_run_deploys_from_source_ref_and_stamps_provenance(monkeypatch):
    """
    `run coverage <static-app> --source-ref <b> --platform-ref <b>` on docker:
    the app deploys from source@<b> and the run is stamped with the composition.
    """
    # The conftest isolates the Lab to a tmp DB, but the spawned engine writes to
    # its real default store; point the Lab's read path at that same file.
    shared = Path.home() / ".hop3" / "test-results.db"
    monkeypatch.setenv("TESTLAB_DB_PATH", str(shared))
    get_session_factory.cache_clear()

    repo = find_project_root()
    ref = _current_branch(repo)  # a deployable branch that carries the apps

    ran = run_once(
        "docker",
        trigger="e2e-compose",
        mode="smoke",
        spec=RunSpec(
            source=Source("local", str(repo)),
            source_ref=ref,
            selector=STATIC_APP,
            platform_ref=ref,
        ),
    )
    assert ran is True  # lease acquired + run executed (not "busy")

    factory = get_session_factory(str(TestlabConfig.get_instance().DB_PATH))
    with factory() as session:
        runs = RunsRepository(session)
        run = next(
            (r for r in runs.list_recent(limit=5) if r.trigger == "e2e-compose"), None
        )
        assert run is not None, "the composition run was not recorded"
        meta = run.run_metadata or {}
        assert meta.get("apps_ref") == ref  # apps came from this ref
        assert meta.get("platform_ref") == ref  # against this platform ref
        assert meta.get("source_name") == "local"
        assert "runner_version" in meta
        # the app was actually deployed and validated, not just recorded
        results = runs.results_for(run)
        assert any(STATIC_APP in r.test_name for r in results)
