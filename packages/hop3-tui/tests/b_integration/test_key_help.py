# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Every key a screen advertises must be a key it binds, and vice versa.

The dashboard used to advertise four "quick actions" in a hand-written string:
`[d] Deploy new app`, `[b] Create backup`, `[l] View system logs`, `[c] Open chat`.
Three were wrong — `d` switched to the dashboard you were already on, `b` opened
the backups list rather than creating one, and `l` was bound to nothing at all.
Nothing could notice, because the text and the bindings had no relationship.

So the help and the panel are now built from each screen's `KEYS`, and this
compares `KEYS` against what `bind` actually receives when the screen renders.
"""

from __future__ import annotations

import pytest
from hop3_tui.app import FOOTER_BINDINGS, Hop3TUI, help_text
from hop3_tui.config import TUIConfig
from hop3_tui.screens import SCREENS, Screen, _common as common, screen_keys
from turbodesk import Size
from turbodesk.events import Key
from turbodesk.testing import render, to_text

SIZE = Size(90, 24)

#: How a `Key` member is spelled in the help text.
KEY_NAMES = {Key.ENTER: "enter", Key.TAB: "tab", " ": "space"}


@pytest.fixture
def hop3() -> Hop3TUI:
    return Hop3TUI(TUIConfig(server_url="http://localhost:1"))


def bound_keys(monkeypatch, hop3: Hop3TUI, screen: Screen) -> set[str]:
    """Render `screen` and collect what it passed to `bind`."""
    seen: set[str] = set()
    real = common.bind

    def spy(ui, actions):
        seen.update(KEY_NAMES.get(k, k) for k in actions)
        return real(ui, actions)

    for module in ("_common", *[s.value for s in Screen], "_logview"):
        monkeypatch.setattr(f"hop3_tui.screens.{module}.bind", spy, raising=False)

    def wrapper(ui):
        with ui.scope(screen):
            return SCREENS[screen](
                ui,
                hop3,
                SIZE,
                argument="blog",
                push=lambda *_: None,
                switch=lambda _: None,
            )

    render(wrapper, size=SIZE)
    return seen


#: Advertised keys that a widget provides rather than `bind`. Listed explicitly so
#: the exception stays small and visible: `enter` on a table is its `on_select`.
WIDGET_KEYS = {Screen.APPS: {"enter"}}


@pytest.mark.parametrize("screen", list(Screen), ids=lambda s: s.value)
def test_a_screen_advertises_every_key_it_binds(monkeypatch, hop3, screen):
    """No undocumented keys: whatever `bind` gets must appear in the help."""
    advertised = {key for key, _ in screen_keys(screen)}

    assert bound_keys(monkeypatch, hop3, screen) <= advertised


@pytest.mark.parametrize("screen", list(Screen), ids=lambda s: s.value)
def test_a_screen_binds_every_key_it_advertises(monkeypatch, hop3, screen):
    """And no dead ones: this is the defect the dashboard panel had, three times."""
    advertised = {key for key, _ in screen_keys(screen)}
    if not advertised:
        pytest.skip(f"{screen.value} declares no keys of its own")

    live = bound_keys(monkeypatch, hop3, screen) | WIDGET_KEYS.get(screen, set())

    assert advertised <= live


def test_the_dashboard_panel_lists_only_keys_it_binds(monkeypatch, hop3):
    """The specific regression: three of four advertised actions did nothing."""

    def wrapper(ui):
        with ui.scope(Screen.DASHBOARD):
            return SCREENS[Screen.DASHBOARD](
                ui, hop3, SIZE, argument="", push=lambda *_: None, switch=lambda _: None
            )

    text = to_text(render(wrapper, size=SIZE))

    for gone in ("Deploy new app", "Create backup", "Open chat"):
        assert gone not in text, f"{gone!r} advertised a key the dashboard never bound"
    assert "System logs" in text


def test_help_shows_more_than_the_footer(monkeypatch, hop3):
    """`?` used to repeat the footer verbatim, which is why it read as useless."""
    text = help_text(Screen.APPS)

    for key, label in FOOTER_BINDINGS:
        assert f"{key:<6} {label}" in text
    # The part the footer has no room for, and the reason to press `?` at all.
    for key, label in screen_keys(Screen.APPS):
        assert f"{key:<6} {label}" in text


def test_help_says_so_for_a_screen_with_no_keys_of_its_own():
    assert "no keys of its own" in help_text(Screen.SYSTEM_LOGS) or screen_keys(
        Screen.SYSTEM_LOGS
    )
