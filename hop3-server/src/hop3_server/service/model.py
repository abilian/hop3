# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from attr import frozen
from hop3_server.service.constants import HOME, LOG_ROOT
from hop3_server.service.logs import multi_tail


@frozen
class App:
    name: str
    is_running: bool = False

    def get_logs(self) -> list[str]:
        logfiles = list(Path(LOG_ROOT, self.name).glob(".*.log"))
        lines = [line.strip() for line in multi_tail(logfiles)]
        return lines

    @property
    def status(self) -> str:
        return "running"

    @property
    def worker_count(self) -> int:
        return 1

    def check_exists(self) -> None:
        if not Path(HOME, self.name).exists():
            raise ValueError(f"App {self.name} does not exist")
