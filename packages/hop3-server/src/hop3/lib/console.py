# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys

__all__ = [
    "Abort",
    "CapturingConsole",
    "black",
    "blue",
    "bold",
    "capture_logs",
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
            case "cyan":
                print(cyan(msg))
            case "magenta":
                print(magenta(msg))
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


class CapturingConsole(Console):
    """A console that captures messages and also prints them.

    Used during deployment to collect logs that can be returned to the client.
    """

    def __init__(self, verbosity: int = 1) -> None:
        """Initialize with verbosity level.

        Args:
            verbosity: 0=quiet, 1=normal, 2=verbose, 3=debug
        """
        self.buffer: list[dict] = []
        self.verbosity = verbosity
        self._printer = PrintingConsole()

    def echo(self, msg, fg: str = "", level: int = 0) -> None:
        """Capture message to buffer and optionally print."""
        # Always capture
        self.buffer.append({"msg": msg, "fg": fg, "level": level})
        # Print based on verbosity
        if level <= self.verbosity:
            self._printer.echo(msg, fg=fg)

    def reset(self) -> None:
        """Clear the buffer."""
        self.buffer.clear()

    def output(self) -> str:
        """Return captured messages as a single string."""
        return "\n".join(entry["msg"] for entry in self.buffer)

    def get_logs(self, max_level: int | None = None) -> list[dict]:
        """Get captured logs up to a certain level.

        Args:
            max_level: Maximum level to include (None = all)

        Returns:
            List of log entries
        """
        if max_level is None:
            return self.buffer.copy()
        return [entry for entry in self.buffer if entry.get("level", 0) <= max_level]


def get_console() -> Console:
    """Return the console object used for logging."""
    # Useful for developing
    testing = "PYTEST_VERSION" in environ
    if testing:
        return TestingConsole()
    return PrintingConsole()


# Global console instance - can be temporarily replaced
_console: Console = get_console()


def get_current_console() -> Console:
    """Get the current console instance."""
    return _console


def set_console(new_console: Console) -> Console:
    """Set the console and return the old one."""
    global _console
    old = _console
    _console = new_console
    return old


# For backward compatibility
console = _console


def echo(msg: str, fg: str = "") -> None:
    """Print message using current console."""
    _console.echo(msg, fg=fg)


def log(msg: str, level: int = 0, fg: str = "green") -> None:
    """Log a message to the console.

    Args:
        msg: Message to log
        level: Indentation/verbosity level (0=important, 1=normal, 2=verbose, 3=debug)
        fg: Foreground color
    """
    formatted = f"{'-' * level}> {msg}" if level > 0 else f"> {msg}"
    # If using CapturingConsole, pass the level
    if isinstance(_console, CapturingConsole):
        _console.echo(formatted, fg=fg, level=level)
    else:
        _console.echo(formatted, fg=fg)


class CaptureLogs:
    """Context manager to capture logs during execution.

    Usage:
        with capture_logs(verbosity=2) as captured:
            do_deploy(app)
        logs = captured.get_logs()

    Args:
        verbosity: 0=quiet, 1=normal (default), 2=verbose, 3=debug
    """

    def __init__(self, verbosity: int = 1) -> None:
        self.verbosity = verbosity
        self.console: CapturingConsole | None = None
        self.old_console: Console | None = None

    def __enter__(self) -> CapturingConsole:
        self.console = CapturingConsole(verbosity=self.verbosity)
        self.old_console = set_console(self.console)
        return self.console

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.old_console is not None:
            set_console(self.old_console)


capture_logs = CaptureLogs


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
