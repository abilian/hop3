# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The bounded queue every background build goes through.

A build is the heaviest thing this server does: it compiles, it downloads, it
fills the page cache, and it does so on the same box as every running app. One
thread per deploy meant the number of concurrent builds was chosen by whoever
called the RPC, so twenty `hop3 deploy` calls became twenty simultaneous
builds, and the apps already running paid for it. That is the "apps must
coexist without interference" rule going unenforced.

So builds run `workers` at a time, and a bounded number may wait. Past that,
a deploy is refused with a message saying so — the queue never grows without
limit, and a refusal is never silent.

Workers are daemon threads, deliberately: a server restart should not block
behind a twenty-minute Nix build. That an interrupted build leaves its app
half-deployed is true here as it was before, and is the state reconciler's
problem rather than this queue's.
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

from hop3.config import HopConfig
from hop3.lib.logging import server_log

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["BuildQueue", "BuildQueueFullError", "get_build_queue"]


class BuildQueueFullError(RuntimeError):
    """Raised when every build slot is busy and the wait line is full."""


class BuildQueue:
    """
    Runs jobs on a fixed number of daemon threads, with a bounded wait line.

    One instance serves the whole server (see :func:`get_build_queue`); the
    class is instantiable so tests can drive a small one without touching it.
    """

    def __init__(self, workers: int, max_waiting: int) -> None:
        if workers < 1:
            msg = f"BuildQueue needs at least one worker, got {workers}"
            raise ValueError(msg)
        self.workers = workers
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue(maxsize=max_waiting)
        self._lock = threading.Lock()
        self._active = 0
        self._threads_started = False

    def submit(self, job: Callable[[], None]) -> int:
        """
        Queue ``job`` and return how many jobs are ahead of it.

        A return of less than ``workers`` means it starts at once. The caller
        is expected to tell the operator when it does not: a build that has not
        started looks exactly like a build that has stalled.

        Raises:
            BuildQueueFullError: the wait line is full; nothing was queued.
        """
        self._start_threads()
        with self._lock:
            ahead = self._active + self._queue.qsize()
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            server_log.warning(
                "Build queue full, deploy refused",
                workers=self.workers,
                waiting=self._queue.qsize(),
            )
            msg = (
                f"Deployer can't start this build: {self.workers} are already "
                f"running and the wait line is full ({self._queue.maxsize} "
                f"deploys). Retry once the running builds finish; "
                f"`hop3 app list` shows what is deploying."
            )
            raise BuildQueueFullError(msg) from None
        return ahead

    def _start_threads(self) -> None:
        """Start the worker threads on first use, once."""
        with self._lock:
            if self._threads_started:
                return
            self._threads_started = True
            for i in range(self.workers):
                thread = threading.Thread(
                    target=self._run_jobs, name=f"hop3-build-{i}", daemon=True
                )
                thread.start()

    def _run_jobs(self) -> None:
        """Take jobs forever. A job that raises must not kill its worker."""
        while True:
            job = self._queue.get()
            with self._lock:
                self._active += 1
            try:
                job()
            except Exception as e:
                # The job owns reporting its own failure (a deploy reports
                # through its stream). Reaching here means it failed to do
                # even that, which is worth a line of its own.
                server_log.error(
                    "Build job raised past its own error handling",
                    error_type=type(e).__name__,
                    error=str(e),
                )
            finally:
                with self._lock:
                    self._active -= 1
                self._queue.task_done()


_build_queue: BuildQueue | None = None
_build_queue_lock = threading.Lock()


def get_build_queue() -> BuildQueue:
    """
    The server's build queue, sized from config on first use.

    Built lazily rather than at import so that a test (or an operator's
    ``HOP3_*`` settings) is read at the point of use, not at import time.
    """
    global _build_queue  # ruff:ignore[global-statement] -- one queue per process
    with _build_queue_lock:
        if _build_queue is None:
            config = HopConfig.get_instance()
            _build_queue = BuildQueue(
                workers=config.MAX_CONCURRENT_BUILDS,
                max_waiting=config.MAX_WAITING_BUILDS,
            )
        return _build_queue
