# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys

__all__ = [
    "Abort",
    "black",
    "blue",
    "bold",
    "console",
    "cyan",
    "debug",
    "dim",
    "echo",
    "error",
    "green",
    "info",
    "log",
    "magenta",
    "panic",
    "red",
    "success",
    "warning",
    "yellow",
]

from abc import ABC, abstractmethod

from attrs import field, frozen
from termcolor import colored

from hop3.system.constants import HOP3_TESTING

# TODO ?
# "light_grey": 37,
# "dark_grey": 90,
# "light_red": 91,
# "light_green": 92,
# "light_yellow": 93,
# "light_blue": 94,
# "light_magenta": 95,
# "light_cyan": 96,
# "white": 97,


# Color helpers
def black(text):
    return colored(text, "black")


def red(text):
    return colored(text, "red")


def green(text):
    return colored(text, "green")


def yellow(text):
    return colored(text, "yellow")


def blue(text):
    return colored(text, "blue")


def magenta(text):
    return colored(text, "magenta")


def cyan(text):
    return colored(text, "cyan")


# Variants
def bold(text):
    return colored(text, attrs=["bold"])


def dim(text):
    return colored(text, attrs=["dark"])


success = green
error = red
warning = yellow
info = blue
debug = dim


class Console(ABC):
    @abstractmethod
    def echo(self, msg, fg: str = ""):
        """Print message to stdout."""

    def reset(self) -> None:  # noqa: B027
        pass

    def output(self) -> str:
        return ""


class PrintingConsole(Console):
    def echo(self, msg, fg: str = "") -> None:
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

    def echo(self, msg, fg: str = "") -> None:
        """Print message to buffer."""
        self.buffer.append(msg)

    def reset(self) -> None:
        del self.buffer[:]

    def output(self) -> str:
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
