# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Console output abstraction for testing framework.

This module provides a structured console abstraction that separates
what to say from how to present it. It supports:
- Multiple verbosity levels (quiet, normal, verbose)
- Semantic output methods (status, progress, success, error)
- Phase/context tracking for structured output
- Both terminal output and test capture
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any

from attrs import define, field
from termcolor import colored

__all__ = [
    "Console",
    "PrintingConsole",
    "Verbosity",
    "blue",
    "bold",
    "cyan",
    "debug",
    "dim",
    "error",
    "green",
    "info",
    "magenta",
    "red",
    "success",
    "warning",
    "yellow",
]


# -----------------------------------------------------------------------------
# Verbosity levels
# -----------------------------------------------------------------------------


class Verbosity(Enum):
    """Console verbosity levels."""

    QUIET = auto()  # Only errors
    NORMAL = auto()  # Standard output
    VERBOSE = auto()  # Detailed output


# -----------------------------------------------------------------------------
# Color helpers (backward compatible)
# -----------------------------------------------------------------------------


def red(text: str) -> str:
    return colored(text, "red")


def green(text: str) -> str:
    return colored(text, "green")


def yellow(text: str) -> str:
    return colored(text, "yellow")


def blue(text: str) -> str:
    return colored(text, "blue")


def magenta(text: str) -> str:
    return colored(text, "magenta")


def cyan(text: str) -> str:
    return colored(text, "cyan")


def bold(text: str) -> str:
    return colored(text, attrs=["bold"])


def dim(text: str) -> str:
    return colored(text, attrs=["dark"])


# Semantic color aliases
success = green
error = red
warning = yellow
info = blue
debug = dim


# -----------------------------------------------------------------------------
# Console ABC
# -----------------------------------------------------------------------------


class Console(ABC):
    """Abstract base class for console operations.

    This defines an interface for structured console output that separates
    the semantics of what to output from the presentation.
    """

    @property
    @abstractmethod
    def verbosity(self) -> Verbosity:
        """Current verbosity level."""

    @abstractmethod
    def set_verbosity(self, level: Verbosity) -> None:
        """Set verbosity level."""

    # Low-level output
    @abstractmethod
    def echo(self, msg: str, fg: str = "") -> None:
        """Print message with optional color."""

    # High-level semantic output
    @abstractmethod
    def status(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Print a status message (normal verbosity)."""

    @abstractmethod
    def progress(self, message: str, current: int = 0, total: int = 0) -> None:
        """Print a progress message (normal verbosity)."""

    @abstractmethod
    def success(self, message: str) -> None:
        """Print a success message (normal verbosity)."""

    @abstractmethod
    def error(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Print an error message (always shown)."""

    @abstractmethod
    def warning(self, message: str) -> None:
        """Print a warning message (normal verbosity)."""

    @abstractmethod
    def info(self, message: str) -> None:
        """Print an info message (verbose only)."""

    @abstractmethod
    def debug(self, message: str) -> None:
        """Print a debug message (verbose only)."""

    # Phase tracking
    @abstractmethod
    def start_phase(self, phase: str) -> None:
        """Start a named phase (e.g., 'deploy', 'test')."""

    @abstractmethod
    def end_phase(self, phase: str, success: bool = True) -> None:
        """End the current phase."""

    # Section formatting
    @abstractmethod
    def header(self, title: str, width: int = 70) -> None:
        """Print a section header."""

    @abstractmethod
    def separator(self, char: str = "=", width: int = 70) -> None:
        """Print a separator line."""

    # Testing support (non-abstract with default implementations)
    def output(self) -> str:
        """Return buffered output (for testing)."""
        return ""


# -----------------------------------------------------------------------------
# PrintingConsole - Terminal output
# -----------------------------------------------------------------------------


@define
class PrintingConsole(Console):
    """Console that prints to stdout with colors."""

    _verbosity: Verbosity = field(default=Verbosity.NORMAL)
    _current_phase: str | None = field(default=None)

    @property
    def verbosity(self) -> Verbosity:
        return self._verbosity

    def set_verbosity(self, level: Verbosity) -> None:
        self._verbosity = level

    def echo(self, msg: str, fg: str = "") -> None:
        """Print message with optional color."""
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
            case "dim":
                print(dim(msg))
            case _:
                print(msg)

    def status(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Print a status message."""
        if self._verbosity == Verbosity.QUIET:
            return
        print(message)
        if details and self._verbosity == Verbosity.VERBOSE:
            for key, value in details.items():
                print(dim(f"  {key}: {value}"))

    def progress(self, message: str, current: int = 0, total: int = 0) -> None:
        """Print a progress message."""
        if self._verbosity == Verbosity.QUIET:
            return
        if total > 0:
            print(f"  {message} ({current}/{total})")
        else:
            print(f"  {message}")

    def success(self, message: str) -> None:
        """Print a success message."""
        if self._verbosity == Verbosity.QUIET:
            return
        print(green(f"✓ {message}"))

    def error(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Print an error message (always shown)."""
        print(red(f"✗ {message}"))
        if details:
            for key, value in details.items():
                print(red(f"  {key}: {value}"))

    def warning(self, message: str) -> None:
        """Print a warning message."""
        if self._verbosity == Verbosity.QUIET:
            return
        print(yellow(f"⚠ {message}"))

    def info(self, message: str) -> None:
        """Print an info message (verbose only)."""
        if self._verbosity != Verbosity.VERBOSE:
            return
        print(blue(f"ℹ {message}"))

    def debug(self, message: str) -> None:
        """Print a debug message (verbose only)."""
        if self._verbosity != Verbosity.VERBOSE:
            return
        print(dim(f"  [DEBUG] {message}"))

    def start_phase(self, phase: str) -> None:
        """Start a named phase."""
        if self._verbosity == Verbosity.QUIET:
            return
        self._current_phase = phase
        print(f"\n[{phase.upper()}]")

    def end_phase(self, phase: str, success: bool = True) -> None:
        """End the current phase."""
        if self._verbosity == Verbosity.QUIET:
            return
        status = green("✓") if success else red("✗")
        print(f"{status} {phase} completed")
        self._current_phase = None

    def header(self, title: str, width: int = 70) -> None:
        """Print a section header."""
        if self._verbosity == Verbosity.QUIET:
            return
        print("\n" + "=" * width)
        print(bold(title))
        print("=" * width)

    def separator(self, char: str = "=", width: int = 70) -> None:
        """Print a separator line."""
        if self._verbosity == Verbosity.QUIET:
            return
        print(char * width)
