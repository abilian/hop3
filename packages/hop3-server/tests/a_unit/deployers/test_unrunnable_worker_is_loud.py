# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A worker that cannot be executed must fail the deploy, not race it.

bugsink runs gunicorn plus `bugsink-runsnappea`, which drains its background
queue. When the worker's command was not on PATH the daemon died the instant
uWSGI spawned it, was respawned, and died again — but uWSGI only announces that
it is throttling after several cycles. Whether that announcement landed before
or after the web process answered its first request decided the verdict: the
same broken app passed on an idle box and failed on a busy one, and when it
passed, the queue was dead behind a login page that rendered perfectly.
"""

from __future__ import annotations

from hop3.deployers.deployer import _unrunnable_worker


def test_a_missing_worker_command_is_recognised() -> None:
    """dash's wording, which is what runs `sh -c` on Debian."""
    line = "sh: 1: exec: bugsink-runsnappea: not found"

    assert _unrunnable_worker(["starting uWSGI", line]) == line


def test_bashs_wording_is_recognised_too() -> None:
    """The shell is whatever /bin/sh points at, and they word it differently."""
    line = "sh: line 1: exec: celery: not found"

    assert _unrunnable_worker([line]) == line


def test_a_non_executable_command_counts() -> None:
    """Present but not executable fails just as completely as absent."""
    line = "sh: 1: exec: ./manage.sh: Permission denied"

    assert _unrunnable_worker([line]) == line


def test_an_ordinary_log_is_not_a_failure() -> None:
    """The app's own output must not be read as a broken worker."""
    lines = [
        "[INFO] Starting gunicorn 25.1.0",
        "WARNING: template not found: 404.html",
        "denied permission to /tmp/cache, falling back",
    ]

    assert _unrunnable_worker(lines) == ""


def test_the_first_failure_is_reported() -> None:
    """With several, name the one that happened first."""
    lines = [
        "sh: 1: exec: first-worker: not found",
        "sh: 1: exec: second-worker: not found",
    ]

    assert _unrunnable_worker(lines) == "sh: 1: exec: first-worker: not found"
