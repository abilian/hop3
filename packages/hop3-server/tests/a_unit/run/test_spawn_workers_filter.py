# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""The spawner must never hand a lifecycle hook to uWSGI as a daemon.

A Procfile `prebuild:` is a build step, not a persistent process. The
`AppLauncher.workers` fallback (config.workers, used when the build artifact has
no runtime workers) used to leak it — uWSGI then respawned it forever, e.g. an
Elixir app looping `mix release --overwrite` and racing the web worker for the
release binary (`bin/<app>: not found`).
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3.run.spawn import AppLauncher


def _launcher(*, config_workers: dict, artifact_workers: dict | None = None):
    """An AppLauncher seeded only with what the `workers` property reads."""
    launcher = AppLauncher.__new__(AppLauncher)
    launcher.app_name = "myapp"
    launcher.config = SimpleNamespace(workers=config_workers)
    launcher.artifact = (
        None
        if artifact_workers is None
        else SimpleNamespace(runtime=SimpleNamespace(workers=artifact_workers))
    )
    return launcher


def test_fallback_filters_lifecycle_hooks() -> None:
    # No artifact runtime workers → falls back to config.workers; the Procfile
    # prebuild must be filtered out, not spawned as a daemon.
    launcher = _launcher(config_workers={"prebuild": "mix release", "web": "start"})
    assert launcher.workers == {"web": "start"}


def test_artifact_workers_also_filtered() -> None:
    launcher = _launcher(
        config_workers={"web": "start"},
        artifact_workers={"prebuild": "x", "postbuild": "y", "web": "start"},
    )
    assert launcher.workers == {"web": "start"}


def test_plain_app_workers_unaffected() -> None:
    launcher = _launcher(
        config_workers={"web": "gunicorn app:app", "worker": "celery -A t worker"}
    )
    assert launcher.workers == {
        "web": "gunicorn app:app",
        "worker": "celery -A t worker",
    }
