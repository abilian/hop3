# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import sys

from click import secho as echo

__all__ = ["log", "panic", "Abort"]


def log(msg, level=0, fg="green") -> None:
    """Log a message to the console"""

    echo(f"{'-' * level}> {msg}", fg=fg)


def panic(msg):
    log(msg, fg="red")
    sys.exit(1)


class Abort(Exception):  # noqa: N818
    status: int
    msg: str
    explanation: str

    def __init__(
        self, msg: str = "unknown error", status: int = 1, explanation: str = ""
    ):
        if not msg:
            msg = "unknown error"
        self.status = status
        self.msg = msg
        self.explanation = explanation
        log(msg, fg="red")
