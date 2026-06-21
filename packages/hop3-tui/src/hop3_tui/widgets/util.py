# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for Hop3 TUI widgets."""

from __future__ import annotations

__all__ = ["make_bar"]


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
