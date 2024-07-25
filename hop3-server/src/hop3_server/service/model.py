# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hop3_server.service.constants import LOG_ROOT
from hop3_server.service.logs import multi_tail


@dataclass(frozen=True)
class App:
    name: str
    is_running: bool = False

    def get_log_files(self) -> list[str]:
        # logfiles = Path(LOG_ROOT, self.name, process + ".*.log")
        logfiles = list(Path(LOG_ROOT, self.name).glob(".*.log"))

        lines = [line.strip() for line in multi_tail(logfiles)]
        return lines
