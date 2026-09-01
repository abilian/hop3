# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""System resource readout with bar gauges.

Every value here is either what the server reported or a statement that it did not.
The Textual original defaulted the three gauges to the constants 42/63/81 and the
uptime to `14d 3h 22m`, refreshed on a timer so they looked live; an operator reading
a steady 81% disk was reading a literal.
"""

from __future__ import annotations

from typing import NamedTuple

from turbodesk import UI, View, markup, vcat

from hop3_tui.widgets.util import LABEL_WIDTH, UNAVAILABLE, gauge


class SystemStats(NamedTuple):
    """What the panel shows. Immutable, so it is safe to keep in `ui.state`.

    `None` means no measurement, which is not the same as 0%.
    """

    cpu: float | None = None
    memory: float | None = None
    disk: float | None = None
    uptime: str = ""


def status_panel(ui: UI, stats: SystemStats) -> View:
    """CPU, memory and disk as bars, with uptime underneath.

    `gauge` returns markup, which is why this goes through `markup.render` rather
    than `View.text` — the colour is chosen by the threshold, inside the bar.
    """
    rows = [
        markup.render(ui.theme, gauge("CPU", stats.cpu)),
        markup.render(ui.theme, gauge("Memory", stats.memory)),
        markup.render(ui.theme, gauge("Disk", stats.disk)),
        markup.render(
            ui.theme, f"{'Uptime:':<{LABEL_WIDTH}}{stats.uptime or UNAVAILABLE}"
        ),
    ]
    return vcat(rows)
