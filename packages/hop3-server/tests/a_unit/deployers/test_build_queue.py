# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the bounded build queue."""

from __future__ import annotations

import threading

import pytest

from hop3.deployers.build_queue import BuildQueue, BuildQueueFullError


def test_a_job_runs() -> None:
    queue = BuildQueue(workers=1, max_waiting=4)
    ran = threading.Event()

    queue.submit(ran.set)

    assert ran.wait(timeout=5)


def test_no_more_than_workers_run_at_once() -> None:
    """The point of the queue: a burst of deploys is not a burst of builds."""
    queue = BuildQueue(workers=2, max_waiting=8)
    release = threading.Event()
    started = threading.Semaphore(0)
    concurrent = 0
    peak = 0
    lock = threading.Lock()

    def job() -> None:
        nonlocal concurrent, peak
        with lock:
            concurrent += 1
            peak = max(peak, concurrent)
        started.release()
        release.wait(timeout=5)
        with lock:
            concurrent -= 1

    for _ in range(6):
        queue.submit(job)

    # Both workers are busy; the other four are waiting, not building.
    assert started.acquire(timeout=5)
    assert started.acquire(timeout=5)
    with lock:
        assert peak == 2

    release.set()
    queue._queue.join()
    with lock:
        assert peak == 2


def test_the_wait_line_is_bounded() -> None:
    queue = BuildQueue(workers=1, max_waiting=1)
    release = threading.Event()
    running = threading.Event()

    def blocker() -> None:
        running.set()
        release.wait(timeout=5)

    queue.submit(blocker)  # takes the only worker
    assert running.wait(timeout=5)
    queue.submit(lambda: None)  # takes the only waiting place

    with pytest.raises(BuildQueueFullError) as exc_info:
        queue.submit(lambda: None)

    assert "wait line is full" in str(exc_info.value)
    release.set()


def test_submit_reports_how_many_are_ahead() -> None:
    queue = BuildQueue(workers=1, max_waiting=4)
    release = threading.Event()
    running = threading.Event()

    def blocker() -> None:
        running.set()
        release.wait(timeout=5)

    assert queue.submit(blocker) == 0
    assert running.wait(timeout=5)
    # One running, so the next two queue behind it and behind each other.
    assert queue.submit(lambda: None) == 1
    assert queue.submit(lambda: None) == 2

    release.set()


def test_a_raising_job_does_not_kill_its_worker() -> None:
    queue = BuildQueue(workers=1, max_waiting=4)
    ran = threading.Event()

    def explode() -> None:
        msg = "build failed in a way it did not report"
        raise RuntimeError(msg)

    queue.submit(explode)
    queue.submit(ran.set)

    assert ran.wait(timeout=5)


def test_a_queue_needs_a_worker() -> None:
    with pytest.raises(ValueError, match="at least one worker"):
        BuildQueue(workers=0, max_waiting=4)
