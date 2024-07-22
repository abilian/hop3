# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from hop3.system.constants import CRON_REGEXP
from hop3.util.console import Abort, log


def parse_procfile(filename: str | Path) -> dict:
    procfile = Procfile.from_file(filename)
    return procfile.workers


@dataclass(frozen=True)
class Procfile:
    workers: dict = field(default_factory=dict)

    @classmethod
    def from_file(cls, filename: str | Path) -> Procfile:
        path = Path(filename)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filename}")

        procfile = Procfile()
        text = path.read_text()
        procfile.parse(text)
        return procfile

    @classmethod
    def from_str(cls, text: str) -> Procfile:
        procfile = Procfile()
        procfile.parse(text)
        return procfile

    @property
    def web_workers(self) -> dict:
        web_worker_names = {"wsgi", "jwsgi", "rwsgi", "web"}
        return {k: v for k, v in self.workers.items() if k in web_worker_names}

    def parse(self, text: str) -> None:
        """Parses the Procfile.

        Only one worker of each type is allowed.
        """
        for line_number, line in enumerate(text.split("\n")):
            self.parse_line(line, line_number)

        if len(self.workers) == 0:
            return

        # Can't have both 'web' and 'wsgi' workers
        wsgi_worker_types = {"wsgi", "jwsgi", "rwsgi"}
        if wsgi_worker_types.intersection(self.workers) and "web" in self.workers:
            msg = "Error: found both 'wsgi' and 'web' workers"
            raise Abort(msg)

    def parse_line(self, line: str, line_number: int) -> None:
        line = line.strip()
        if line.startswith("#") or not line:
            return

        try:
            kind, command = (x.strip() for x in line.split(":", 1))
        except Exception:
            msg = f"Error: misformatted Procfile entry '{line}' at line {line_number}"
            log(msg, fg="red")
            raise

        # Check for cron patterns
        if kind == "cron":
            self.check_cron(command)

        self.workers[kind] = command

    def check_cron(self, command: str) -> None:
        limits = [59, 24, 31, 12, 7]
        res = re.match(CRON_REGEXP, command)
        if res:
            matches = res.groups()
            for i in range(len(limits)):
                if int(matches[i].replace("*/", "").replace("*", "1")) > limits[i]:
                    raise ValueError(f"Invalid cron pattern: {command}")
