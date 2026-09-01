# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The TUI must show what the server said, or say that it does not know.

Every screen here once rendered invented data behind a normal-looking UI: the log
pane served a hardcoded sample and appended a new fake line roughly every three
seconds, and the system screen reported three constants as live metrics with four
services permanently RUNNING. None of it failed, which is why it lasted — so these
tests assert the absence of the specific fabrications as well as the presence of the
real values.
"""

from __future__ import annotations

import pytest
from hop3_tui.app import Hop3TUI
from hop3_tui.config import TUIConfig
from hop3_tui.screens import SCREENS, Screen
from hop3_tui.screens._logview import status_line
from hop3_tui.widgets import SystemStats, status_panel
from hop3_tui.widgets.util import UNAVAILABLE, gauge
from turbodesk import UI, Size
from turbodesk.testing import render, to_text
from turbodesk.theme import MOCHA

SIZE = Size(78, 16)
# `UNAVAILABLE` is markup; this is what it renders to.
UNAVAILABLE_TEXT = "not reported by the server"


@pytest.fixture
def hop3() -> Hop3TUI:
    return Hop3TUI(TUIConfig(server_url="http://localhost:1"))


def draw_screen(hop3: Hop3TUI, screen: Screen, argument: str = "") -> str:
    def wrapper(ui):
        with ui.scope(screen):
            return SCREENS[screen](
                ui,
                hop3,
                SIZE,
                argument=argument,
                push=lambda *_: None,
                switch=lambda _: None,
            )

    return to_text(render(wrapper, size=SIZE))


# ---------- the log pane ------------------------------------------------


def test_the_log_pane_invents_nothing_when_there_is_nothing(hop3: Hop3TUI):
    """The fabricated eight-line sample used to fill exactly this case."""
    text = draw_screen(hop3, Screen.LOGS, "myapp")

    assert "Nothing logged yet." in text
    # The specific lines the pane used to invent.
    assert "Failed to connect to redis" not in text
    assert "New log entry" not in text
    assert "Server started on port 8000" not in text


def test_a_failed_fetch_stops_the_pane_claiming_to_be_live():
    """A stale pane over a dead connection is the same lie as an invented line."""
    failing = status_line(paused=False, problem="connection refused", count=8)

    assert failing == ("UNREACHABLE", "connection refused", "red")
    # Failure outranks both other states: neither may hide it.
    assert status_line(paused=True, problem="down", count=8).label == "UNREACHABLE"


def test_a_healthy_pane_says_live_and_counts_what_it_has():
    assert status_line(paused=False, problem="", count=8) == (
        "LIVE",
        "8 lines",
        "green",
    )
    assert status_line(paused=True, problem="", count=8).label == "PAUSED"


# ---------- the system screen -------------------------------------------


def test_the_resources_gauge_reports_no_measurement_rather_than_a_number():
    assert gauge("CPU", None).endswith(UNAVAILABLE)
    # The three constants the panel used to assert on a five-second timer.
    for constant in (42.0, 63.0, 81.0):
        assert f"{constant:.0f}%" not in gauge("CPU", None)


def test_the_resources_gauge_renders_a_measurement_when_there_is_one():
    # 0% is a measurement, not a missing one.
    assert "0%" in gauge("Memory", 0.0)
    assert "12%" in gauge("CPU", 12.0)
    assert UNAVAILABLE not in gauge("CPU", 12.0)


def test_the_status_panel_claims_nothing_before_it_is_told():
    text = to_text(status_panel(UI(SIZE, MOCHA), SystemStats()))

    # CPU, memory, disk and uptime.
    assert text.count(UNAVAILABLE_TEXT) == 4
    assert "14d 3h 22m" not in text


def test_the_system_screen_invents_neither_services_nor_a_host(hop3: Hop3TUI):
    text = draw_screen(hop3, Screen.SYSTEM)

    assert "RUNNING" not in text
    assert "nginx" not in text
    assert "hop3.dev" not in text
    assert "v0.5.0" not in text
    assert UNAVAILABLE_TEXT in text


def test_the_dashboard_invents_no_system_stats(hop3: Hop3TUI):
    text = draw_screen(hop3, Screen.DASHBOARD)

    assert "14d 3h 22m" not in text
    for constant in ("42%", "63%", "81%"):
        assert constant not in text
