# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from attr import frozen

from hop3_server.service.constants import LOG_ROOT
from hop3_server.service.logs import multi_tail


@frozen
class App:
    name: str
    is_running: bool = False

    def get_log_files(self) -> list[str]:
        # logfiles = Path(LOG_ROOT, self.name, process + ".*.log")
        logfiles = list(Path(LOG_ROOT, self.name).glob(".*.log"))

        lines = [line.strip() for line in multi_tail(logfiles)]
        return lines
