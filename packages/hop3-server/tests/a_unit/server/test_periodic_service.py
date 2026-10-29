# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""A failed background cycle is logged with its traceback; the loop goes on."""

from __future__ import annotations

import threading
from typing import ClassVar

from hop3.server import periodic_service
from hop3.server.periodic_service import PeriodicService


class _FlakyService(PeriodicService):
    name: ClassVar[str] = "flaky"

    def __init__(self) -> None:
        super().__init__(interval=0.01, initial_delay=0.0)
        self.cycles = 0
        self.second_cycle = threading.Event()

    def run_once(self) -> None:
        self.cycles += 1
        if self.cycles == 1:
            msg = "rootd unreachable"
            raise RuntimeError(msg)
        self.second_cycle.set()


class _RecordingLog:
    def __init__(self) -> None:
        self.exceptions: list[tuple[str, dict]] = []

    def exception(self, message: str, **fields: object) -> None:
        self.exceptions.append((message, fields))


def test_a_failed_cycle_is_logged_with_a_traceback_and_the_loop_continues(
    monkeypatch,
):
    recorded = _RecordingLog()
    monkeypatch.setattr(periodic_service, "server_log", recorded)
    service = _FlakyService()

    service.start()
    try:
        assert service.second_cycle.wait(timeout=2.0)
    finally:
        service.stop()

    assert recorded.exceptions[0] == (
        "Background service cycle failed",
        {"service": "flaky", "error": "rootd unreachable"},
    )
    assert not service.is_running()
