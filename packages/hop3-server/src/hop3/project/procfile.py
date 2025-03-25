# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from hop3 import config as c
from hop3.lib import log


def parse_procfile(filename: str | Path) -> dict:
    """Parse a Procfile to extract process information.

    Input:
    - filename (str | Path): The path to the Procfile to be parsed.

    Returns:
    - dict: A dictionary representing the workers defined in the Procfile.

    Raises:
    - ValueError: If the provided file is syntaxically or semantically incorrect.
    """
    # TODO: introduce a domain-specific exception?
    procfile = Procfile.from_file(filename)
    return procfile.workers


@dataclass(frozen=True)
class Procfile:
    """Represents a parsed Procfile."""

    workers: dict = field(default_factory=dict)

    @classmethod
    def from_file(cls, filename: str | Path) -> Procfile:
        path = Path(filename)
        if not path.exists():
            msg = f"File not found: {filename}"
            raise FileNotFoundError(msg)

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
        """Parse the Procfile.

        Only one worker of each type is allowed.

        Input:
        - text: A string representing the content of a Procfile with each line specifying a worker type.

        Raises:
        - ValueError: If both 'web' and types from 'wsgi' group of workers are found.
        """
        for line_number, line in enumerate(text.split("\n")):
            # Parse each line of the Procfile with its line number
            self.parse_line(line, line_number)

        if len(self.workers) == 0:
            return

        # Can't have both 'web' and 'wsgi' workers
        wsgi_worker_types = {"wsgi", "jwsgi", "rwsgi"}
        if wsgi_worker_types.intersection(self.workers) and "web" in self.workers:
            msg = "Error: found both 'wsgi' and 'web' workers"
            # Raise an error if both 'web' and 'wsgi' workers are present
            raise ValueError(msg)

    def parse_line(self, line: str, line_number: int) -> None:
        """Parse a single line from a Procfile, updating internal worker
        commands or validating cron entries.

        Input:
        - line: A string representing a line from the Procfile.
        - line_number: An integer indicating the line number in the Procfile, used for error messages.
        """
        line = line.strip()

        if line.startswith("#") or not line:
            # Ignore comments and blank lines
            return

        try:
            kind, command = (x.strip() for x in line.split(":", 1))
        except Exception:
            msg = f"Error: misformatted Procfile entry '{line}' at line {line_number}"
            log(msg, fg="red")
            raise

        if kind == "cron":
            self.check_cron(command)

        # Add the parsed command to the
        self.workers[kind] = command

    def check_cron(self, command: str) -> None:
        """Validate a cron command string against predefined limits.

        Input:
        - command: str - A cron command string to be validated.

        Raises:
        - ValueError: If the cron pattern contains values exceeding the allowed limits.
        """
        limits = [59, 24, 31, 12, 7]  # Maximum allowable values for each cron field
        res = re.match(c.CRON_REGEXP, command)
        if res:
            matches = res.groups()
            for i in range(len(limits)):
                # Replace wildcards with '1' or remove step values, then convert to integer
                value = int(matches[i].replace("*/", "").replace("*", "1"))
                if value > limits[i]:
                    # Raise an error if the value exceeds the maximum limit for its field
                    msg = f"Invalid cron pattern: {command}"
                    raise ValueError(msg)
