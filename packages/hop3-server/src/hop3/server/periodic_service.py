# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The background-thread loop shared by the server's maintenance services.

State sync, certificate renewal, domain health and WAF bans each ran the same
start/stop/Event loop, written out four times; one of the copies logged a
failed cycle without its traceback.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import ClassVar

from hop3.lib import log
from hop3.lib.logging import server_log


class PeriodicService(ABC):
    """
    Run `run_once` in a daemon thread every ``interval`` seconds.

    The first cycle runs after ``initial_delay``, which lets the server settle.
    A failed cycle is logged with its traceback and the loop carries on: one bad
    cycle must not stop the maintenance the server relies on.
    """

    #: Thread name, and the service's name in the log.
    name: ClassVar[str]

    def __init__(self, *, interval: float, initial_delay: float) -> None:
        self.interval = interval
        self.initial_delay = initial_delay
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @abstractmethod
    def run_once(self) -> object:
        """One cycle of the service's work. Public so it is testable alone."""

    def start(self) -> None:
        """Start the background thread, unless it already runs."""
        if self.is_running():
            log(f"{self.name} service already running", level=2, fg="yellow")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()
        log(f"{self.name} service started", level=1, fg="green")

    def stop(self, timeout: float = 5.0) -> None:
        """
        Stop the background thread, waiting up to ``timeout`` seconds.

        A thread still in its cycle after ``timeout`` is reported at error
        level and kept, so ``is_running()`` stays true. It does not raise: the
        server's shutdown hook stops every service in turn, and an exception
        here would leave the others running.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                log(
                    f"{self.name} service did not stop within {timeout}s:"
                    " its cycle is still running",
                    level=1,
                    fg="red",
                )
                server_log.error(
                    "Background service did not stop",
                    service=self.name,
                    timeout=timeout,
                )
                return
            self._thread = None
        log(f"{self.name} service stopped", level=1, fg="yellow")

    def is_running(self) -> bool:
        """Is the background thread alive?"""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        delay = self.initial_delay
        while not self._stop_event.wait(delay):
            delay = self.interval
            try:
                self.run_once()
            except Exception as e:
                log(f"{self.name} cycle failed: {e}", level=1, fg="red")
                server_log.exception(
                    "Background service cycle failed", service=self.name, error=str(e)
                )
