# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""The app shell: navigation, chrome, connection state.

The Textual original drove these through `async with app.run_test()` and asserted on
the widget tree via `query_one`. Here the app is a function from `UI` to a `View`, so
the tests render it and assert on what came out.
"""

from __future__ import annotations

import pytest
from hop3_tui.app import ConnectionState, Hop3TUI, Nav, app
from hop3_tui.config import TUIConfig
from hop3_tui.screens import Screen
from turbodesk import Size
from turbodesk.events import Key, KeyPress
from turbodesk.testing import render, to_text

SCREEN = Size(80, 24)


@pytest.fixture
def hop3() -> Hop3TUI:
    """Pointed at a port nothing listens on, so no test touches the network."""
    return Hop3TUI(TUIConfig(server_url="http://localhost:1"))


@pytest.fixture
def screen(hop3: Hop3TUI):
    def draw(events=(), size: Size = SCREEN) -> str:
        return to_text(render(app(hop3), size=size, events=list(events)))

    return draw


# -- navigation state ----------------------------------------------------------------


def test_nav_starts_on_the_dashboard():
    assert Nav().current == (Screen.DASHBOARD, "")


def test_switching_mode_replaces_the_mode():
    assert Nav().switch(Screen.APPS).current == (Screen.APPS, "")


def test_pushing_a_screen_shows_it_over_the_mode():
    nav = Nav().push(Screen.APP_DETAIL, "blog")

    assert nav.current == (Screen.APP_DETAIL, "blog")
    assert nav.mode is Screen.DASHBOARD, "the mode underneath is untouched"


def test_popping_returns_to_what_was_underneath():
    nav = Nav().push(Screen.APP_DETAIL, "blog").pop()

    assert nav.current == (Screen.DASHBOARD, "")


def test_switching_mode_clears_the_stack():
    nav = Nav().push(Screen.APP_DETAIL, "blog").switch(Screen.APPS)

    assert nav.stack == ()


def test_popping_an_empty_stack_is_harmless():
    assert Nav().pop().current == (Screen.DASHBOARD, "")


# -- chrome ---------------------------------------------------------------------------


def test_the_header_shows_the_app_name(screen):
    assert "Hop3" in screen().splitlines()[0]


def test_the_header_shows_the_connection_state(screen):
    assert "Connecting" in screen().splitlines()[0]


def test_the_footer_lists_the_mode_keys(screen):
    footer = screen().splitlines()[-1]

    assert "Dashboard" in footer
    assert "Apps" in footer


def test_the_footer_drops_hints_that_do_not_fit_rather_than_cutting_them(screen):
    """Eight hints do not fit in eighty columns; a half-word would read as a binding."""
    narrow = screen(size=Size(40, 12)).splitlines()[-1]

    assert "Dashboard" in narrow
    assert "Backups" not in narrow, "dropped whole"
    assert len(narrow.rstrip()) <= 40


def test_the_footer_shows_more_hints_when_there_is_room(screen):
    assert "Quit" in screen(size=Size(120, 24)).splitlines()[-1]


def test_the_app_fills_the_screen(hop3: Hop3TUI):
    view = render(app(hop3), size=SCREEN)

    assert view.size == SCREEN


@pytest.mark.parametrize("size", [Size(40, 12), Size(120, 40), Size(80, 24)])
def test_the_app_fills_whatever_screen_it_is_given(hop3: Hop3TUI, size: Size):
    assert render(app(hop3), size=size).size == size


# -- navigating by key ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "marker"),
    [
        ("a", "NAME"),  # the apps table's first column heading
        ("s", "RESOURCES"),
        ("o", "(no add-ons)"),
        ("b", "(no backups)"),
        ("c", "Hop3 console."),
    ],
)
def test_a_mode_key_switches_screen(screen, key: str, marker: str):
    assert marker in screen([KeyPress(key)])


def test_d_returns_to_the_dashboard(screen):
    assert "APPLICATIONS" in screen([KeyPress("a"), KeyPress("d")])


def test_the_dashboard_is_what_shows_first(screen):
    assert "APPLICATIONS" in screen()


def test_switching_away_and_back_does_not_confuse_the_screens(screen):
    """Each screen has its own hook slots; swapping used to hand one screen's state
    to the next. Exercised here because the app is what found it."""
    assert "APPLICATIONS" in screen([KeyPress("a"), KeyPress("s"), KeyPress("d")])


def test_escape_leaves_a_mode_screen(screen):
    assert "APPLICATIONS" in screen([KeyPress("a"), KeyPress(Key.ESCAPE)])


def test_escape_gets_out_of_the_console_where_letters_are_typed(screen):
    """The chat input takes every printable key, so `d` cannot be the way back."""
    assert "APPLICATIONS" in screen([KeyPress("c"), KeyPress(Key.ESCAPE)])


def test_a_letter_typed_into_the_console_does_not_switch_screen(screen):
    assert "Hop3 console." in screen([KeyPress("c"), KeyPress("d")])


def test_an_unbound_key_changes_nothing(screen):
    assert screen([KeyPress("z")]) == screen()


# -- connection state -----------------------------------------------------------------


def test_a_fresh_app_is_connecting(hop3: Hop3TUI):
    assert hop3.connection_state is ConnectionState.CONNECTING


def test_one_failure_does_not_disconnect(hop3: Hop3TUI):
    hop3.mark_api_failure()

    assert hop3.connection_state is not ConnectionState.DISCONNECTED


def test_three_failures_disconnect(hop3: Hop3TUI):
    for _ in range(3):
        hop3.mark_api_failure()

    assert hop3.connection_state is ConnectionState.DISCONNECTED


def test_a_success_clears_the_failure_count(hop3: Hop3TUI):
    hop3.mark_api_failure()
    hop3.mark_api_failure()
    hop3.mark_api_success()
    hop3.mark_api_failure()

    assert hop3.connection_state is ConnectionState.CONNECTED


@pytest.mark.asyncio
async def test_a_failed_health_check_is_recorded(hop3: Hop3TUI):
    """Nothing listens on port 1, so this exercises the real failure path."""
    await hop3.check_connection()

    assert hop3.consecutive_failures == 1
