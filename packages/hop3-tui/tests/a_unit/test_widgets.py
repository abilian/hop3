# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""The hop3-specific views.

In the original these were `Static` subclasses with reactive attributes; the tests
mounted them in a throwaway `App` and poked the attributes. Here they are functions, so
the tests call them.
"""

from __future__ import annotations

import pytest
from hop3_tui.api.models import AppState
from hop3_tui.widgets import SystemStats, footer, header, make_bar, panel, status_panel
from hop3_tui.widgets.status_badge import state_style, status_badge
from turbodesk import UI, Size, View, vcat
from turbodesk.testing import to_text
from turbodesk.theme import MOCHA

SIZE = Size(60, 12)


@pytest.fixture
def ui() -> UI:
    return UI(SIZE, MOCHA)


# -- the bar gauge --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("percent", "filled"), [(0, 0), (50, 5), (100, 10), (42, 4), (81, 8)]
)
def test_a_bar_fills_in_proportion(percent: float, filled: int):
    assert make_bar(percent).count("█") == filled


def test_a_bar_is_always_the_width_asked_for():
    bar = make_bar(37, width=20)

    assert bar.count("█") + bar.count("░") == 20


@pytest.mark.parametrize(
    ("percent", "colour"), [(10, "green"), (75, "yellow"), (95, "red")]
)
def test_a_bar_changes_colour_at_the_thresholds(percent: float, colour: str):
    assert f"[{colour}]" in make_bar(percent)


# -- status badge ---------------------------------------------------------------------


def test_a_badge_shows_the_state_name(ui: UI):
    assert "RUNNING" in to_text(status_badge(ui.theme, AppState.RUNNING))


@pytest.mark.parametrize("state", list(AppState))
def test_every_state_has_a_badge(ui: UI, state: AppState):
    assert state.value in to_text(status_badge(ui.theme, state))


def test_a_running_badge_is_green(ui: UI):
    assert state_style(ui.theme, AppState.RUNNING).bg == ui.theme.green


def test_a_failed_badge_is_red(ui: UI):
    assert state_style(ui.theme, AppState.FAILED).bg == ui.theme.red


@pytest.mark.parametrize("state", [AppState.STARTING, AppState.STOPPING])
def test_a_transitional_badge_is_yellow(ui: UI, state: AppState):
    assert state_style(ui.theme, state).bg == ui.theme.yellow


def test_a_stopped_badge_is_muted(ui: UI):
    style = state_style(ui.theme, AppState.STOPPED)

    assert style.bg == ui.theme.surface1
    assert not style.bold


# -- status panel ---------------------------------------------------------------------


def test_the_status_panel_labels_every_gauge(ui: UI):
    text = to_text(status_panel(ui, SystemStats(cpu=1, memory=2, disk=3)))

    for label in ("CPU", "Memory", "Disk", "Uptime"):
        assert label in text


def test_the_status_panel_shows_the_percentages(ui: UI):
    text = to_text(status_panel(ui, SystemStats(cpu=42, memory=63, disk=81)))

    assert "42%" in text
    assert "81%" in text


def test_the_status_panel_shows_the_uptime(ui: UI):
    assert "14d" in to_text(status_panel(ui, SystemStats(uptime="14d 3h")))


def test_default_stats_are_unknown_rather_than_zero():
    """0% is a measurement. The panel must not claim one it was never given."""
    assert SystemStats() == SystemStats(None, None, None, "")


# -- chrome ---------------------------------------------------------------------------


# The header shows a clock, so it calls `ui.now`, which registers a tick on the running
# loop. These three are `async` to get one — there is nothing to await, which is what
# `RUF029` is for; the loop is the point.
@pytest.mark.asyncio
async def test_the_header_carries_the_title(ui: UI):
    assert "Hop3" in to_text(header(ui, "Hop3"))


@pytest.mark.asyncio
async def test_the_header_carries_the_subtitle(ui: UI):
    assert "Connected" in to_text(header(ui, "Hop3", "● Connected"))


@pytest.mark.asyncio
async def test_the_header_is_one_row_the_width_of_the_screen(ui: UI):
    view = header(ui, "Hop3", "● Connected")

    assert view.height == 1
    assert view.width == SIZE.width


def test_the_footer_shows_the_keys_it_is_given(ui: UI):
    text = to_text(footer(ui, [("q", "Quit"), ("?", "Help")]))

    assert "Quit" in text
    assert "Help" in text


def test_the_footer_is_one_row_the_width_of_the_screen(ui: UI):
    view = footer(ui, [("q", "Quit")])

    assert view.height == 1
    assert view.width == SIZE.width


def test_an_empty_footer_is_still_a_full_row(ui: UI):
    assert footer(ui, []).width == SIZE.width


def test_the_footer_never_cuts_a_label_in_half(ui: UI):
    """`q  Q` would read as a binding rather than as truncation."""
    many = [(str(n), f"Action{n}") for n in range(20)]

    text = to_text(footer(ui, many)).rstrip()

    assert len(text) <= SIZE.width
    assert not text.endswith("Action")


# -- panels ---------------------------------------------------------------------------


def test_a_panel_shows_its_title(ui: UI):
    assert "STUFF" in to_text(panel(ui, "Stuff", View.text("body"), Size(30, 8)))


def test_a_panel_shows_its_body(ui: UI):
    assert "body" in to_text(panel(ui, "Stuff", View.text("body"), Size(30, 8)))


def test_a_panel_is_drawn_at_the_size_it_was_given(ui: UI):
    view = panel(ui, "Stuff", View.text("body"), Size(30, 8))

    assert view.size == Size(30, 8)


def test_a_panel_can_be_accented(ui: UI):
    plain = panel(ui, "S", View.text("b"), Size(20, 6))
    accented = panel(ui, "S", View.text("b"), Size(20, 6), accent=True)

    assert to_text(plain) == to_text(accented), "same text"
    assert plain.to_grid(Size(20, 6)) != accented.to_grid(Size(20, 6)), (
        "different colour"
    )


def test_an_overlong_body_is_cropped_to_the_panel(ui: UI):
    long_body = vcat([View.text(f"line {n}") for n in range(50)])

    assert panel(ui, "S", long_body, Size(20, 6)).size == Size(20, 6)


def test_a_cropped_panel_says_it_is_cropped(ui: UI):
    """Without a layout engine, a row that silently vanishes reads as a data bug."""
    long_body = vcat([View.text(f"line {n}") for n in range(50)])

    assert "…" in to_text(panel(ui, "S", long_body, Size(20, 6)))


def test_a_panel_with_room_to_spare_is_not_marked(ui: UI):
    assert "…" not in to_text(panel(ui, "S", View.text("body"), Size(30, 10)))
