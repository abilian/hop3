# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Hop3-specific views.

In Textual these were `Static` subclasses with `reactive` attributes and a `watch_*`
method per attribute to trigger a redraw. Here they are plain functions of the values
they display — there is nothing to keep between frames, so there is nothing to watch.
"""

from __future__ import annotations

from .chrome import footer, header, panel, panel_title
from .status_badge import status_badge
from .status_panel import SystemStats, status_panel
from .util import make_bar

__all__ = [
    "SystemStats",
    "footer",
    "header",
    "make_bar",
    "panel",
    "panel_title",
    "status_badge",
    "status_panel",
]
