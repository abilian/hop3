# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for Hop3 TUI widgets."""

from __future__ import annotations

__all__ = ["LABEL_WIDTH", "UNAVAILABLE", "gauge", "make_bar"]

#: Shown wherever the server has not (yet) supplied a value. `0%` is a measurement
#: and a plausible constant is a lie, so an unknown has to say that it is one.
UNAVAILABLE = "[dim]not reported by the server[/]"

LABEL_WIDTH = 8


def make_bar(percent: float, width: int = 10) -> str:
    """Create a progress bar string."""
    filled = int(percent / 100 * width)
    empty = width - filled

    # Color based on percentage
    if percent >= 90:
        color = "red"
    elif percent >= 70:
        color = "yellow"
    else:
        color = "green"

    return f"[{color}]{'█' * filled}[/][dim]{'░' * empty}[/]"


def gauge(label: str, percent: float | None) -> str:
    """A labelled bar and a number, or a statement that there is no measurement."""
    value = UNAVAILABLE if percent is None else f"{make_bar(percent)} {percent:.0f}%"
    return f"{label + ':':<{LABEL_WIDTH}}{value}"
