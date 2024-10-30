# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys

__all__ = ["Abort", "echo", "log", "panic"]

from cleez.colors import blue, green, red, yellow


def echo(msg, fg: str = ""):
    """Print message to stdout."""
    match fg:
        case "" | "white":
            print(msg)
        case "green":
            print(green(msg))
        case "red":
            print(red(msg))
        case "blue":
            print(blue(msg))
        case "yellow":
            print(yellow(msg))
        case _:
            raise ValueError(f"Unknown color: {fg}")


def log(msg, level=0, fg="green") -> None:
    """Log a message to the console."""
    echo(f"{'-' * level}> {msg}", fg=fg)


def panic(msg) -> None:
    log(msg, fg="red")
    sys.exit(1)


class Abort(Exception):  # noqa: N818
    status: int
    msg: str
    explanation: str

    def __init__(
        self,
        msg: str = "unknown error",
        status: int = 1,
        explanation: str = "",
    ) -> None:
        if not msg:
            msg = "unknown error"
        self.status = status
        self.msg = msg
        self.explanation = explanation
        log(msg, fg="red")
