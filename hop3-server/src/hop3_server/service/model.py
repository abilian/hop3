# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from attr import frozen
from devtools import debug
from hop3_server.service.constants import APP_ROOT, ENV_ROOT, LOG_ROOT
from hop3_server.service.settings import parse_settings


@frozen
class App:
    name: str
    is_running: bool = False

    def get_logs(self) -> list[str]:
        debug(Path(LOG_ROOT, self.name))
        logfiles = list(Path(LOG_ROOT).glob(f"{self.name}.*.log"))
        debug(logfiles)
        lines = []
        for logfile in logfiles:
            lines.extend(logfile.read_text().splitlines())
        return lines

    @property
    def status(self) -> str:
        return "running"

    @property
    def worker_count(self) -> int:
        return 1

    def check_exists(self) -> None:
        debug(APP_ROOT, self.name)
        debug(APP_ROOT / self.name)
        debug(Path(APP_ROOT, self.name))
        if not Path(APP_ROOT, self.name).exists():
            raise ValueError(f"App {self.name} does not exist")

    def get_env(self) -> dict[str, str]:
        virtualenv_path = Path(ENV_ROOT, self.name)
        settings_path = Path(virtualenv_path, "ENV")
        return parse_settings(settings_path)
