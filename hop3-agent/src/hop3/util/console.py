# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys

__all__ = ["Abort", "echo", "log", "panic"]

from abc import ABC, abstractmethod

from attrs import field, frozen
from cleez.colors import blue, green, red, yellow

from hop3.system.constants import HOP3_TESTING


class Console(ABC):
    @abstractmethod
    def echo(self, msg, fg: str = ""):
        """Print message to stdout."""

    def reset(self):
        pass

    def output(self):
        return ""


class PrintingConsole(Console):
    def echo(self, msg, fg: str = ""):
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
                msg = f"Unknown color: {fg}"
                raise ValueError(msg)


@frozen
class TestingConsole(Console):
    buffer: list[str] = field(factory=list)

    def echo(self, msg, fg: str = ""):
        """Print message to buffer."""
        self.buffer.append(msg)

    def reset(self):
        del self.buffer[:]

    def output(self):
        return "\n".join(self.buffer)


console: Console

if HOP3_TESTING:
    console = TestingConsole()
else:
    console = PrintingConsole()

echo = console.echo


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
