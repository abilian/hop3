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
from os import environ

from attrs import field, frozen
from termcolor import colored

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
    """Abstract base class for console operations.

    This defines an interface for console operations such as echoing
    messages with optional foreground colors and handling console
    output.
    """

    @abstractmethod
    def echo(self, msg, fg: str = ""):
        """Print message to stdout."""

    def reset(self) -> None:  # noqa: B027
        pass

    def output(self) -> str:
        return ""


class PrintingConsole(Console):
    """A console capable of printing messages in different colors."""

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
    """A console that captures messages for testing purposes."""

    buffer: list[str] = field(factory=list)

    def echo(self, msg, fg: str = "") -> None:
        """Print a message to the buffer."""
        self.buffer.append(msg)

    def reset(self) -> None:
        """Clear all elements from the buffer."""
        del self.buffer[:]

    def output(self) -> str:
        """Return the contents of the buffer as a single string."""
        return "\n".join(self.buffer)


def get_console() -> Console:
    """Return the console object used for logging."""
    # Useful for developing
    testing = "PYTEST_VERSION" in environ
    if testing:
        return TestingConsole()
    else:
        return PrintingConsole()


console = get_console()
echo = console.echo


def log(msg: str, level=0, fg="green") -> None:
    """Log a message to the console."""
    echo(f"{'-' * level}> {msg}", fg=fg)


def panic(msg: str) -> None:
    """Logs an error message in red and exits the program, with a status code
    of 1, terminating the program."""
    log(msg, fg="red")
    sys.exit(1)


class Abort(Exception):  # noqa: N818
    """Custom exception class to handle abort scenarios with detailed
    information.

    This exception is used to represent an abort event with a status code,
    message, and an optional explanation. It logs the error message when
    instantiated.

    Input:
    - msg: str, optional
        The message describing the reason for the abort. Defaults to "unknown error".
    - status: int, optional
        The status code associated with the abort event. Defaults to 1.
    - explanation: str, optional
        Additional explanation for the abort event. Defaults to an empty string.
    """

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
