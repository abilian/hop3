# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The screens themselves, drawn from a live server.

`test_client_against_server.py` proves each client method against the container. This
proves the layer above it: that a screen, rendering with the real client behind it,
completes its fetch and draws — no exception escaping a spawned coroutine, no parse
error turning a table into a traceback.

turbodesk records a failure raised inside a task and re-raises it on the next render
(`ui._failure`), so a screen whose fetch blew up cannot pass here by quietly drawing
its empty state — which is exactly how the stubbed layers missed the drift.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from hop3_testing.targets.constants import create_test_token
from hop3_tui.api.client import Hop3Client
from hop3_tui.app import Hop3TUI, app
from hop3_tui.config import TUIConfig
from hop3_tui.screens import SCREENS, Screen
from turbodesk import Size
from turbodesk.runtime import UI
from turbodesk.testing import to_text
from turbodesk.theme import MOCHA

if TYPE_CHECKING:
    from hop3_testing.targets.base import TargetInfo

SIZE = Size(96, 28)

#: `system` is excluded: it draws no server data of its own, and the one call behind
#: it (`system status`) fails on a supervisor-managed box — see the xfail in
#: `test_client_against_server.py`.
LIVE_SCREENS = [s for s in Screen if s is not Screen.SYSTEM]


@pytest.fixture
def tui(hop3_server: TargetInfo) -> Hop3TUI:
    """A real `Hop3TUI` wired to the container. Nothing is stubbed."""
    handle = Hop3TUI(TUIConfig(server_url=hop3_server.api_url))
    handle.api_client = Hop3Client(
        base_url=hop3_server.api_url,
        token=create_test_token(secret_key=hop3_server.secret_key)
        if hop3_server.secret_key
        else create_test_token(),
    )
    return handle


def draw(render, size: Size = SIZE, rounds: int = 25) -> str:
    """Render until the spawned fetches have settled, then re-raise anything they hit."""

    async def scenario() -> str:
        ui = UI(size, MOCHA)
        view = ui.render(render)
        for _ in range(rounds):
            await asyncio.sleep(0.05)
            if ui._dirty:
                view = ui.render(render)
        if ui._failure is not None:
            raise ui._failure
        return to_text(view)

    return asyncio.run(scenario())


@pytest.mark.parametrize("screen", LIVE_SCREENS, ids=lambda s: s.value)
def test_a_screen_fetches_and_draws_against_a_real_server(tui: Hop3TUI, screen: Screen):
    def render(ui: UI):
        with ui.scope(screen):
            return SCREENS[screen](
                ui,
                tui,
                SIZE,
                argument="no-such-app",
                push=lambda *_: None,
                switch=lambda _: None,
            )

    text = draw(render)

    assert text.strip(), f"{screen.value} drew nothing"


def test_the_whole_app_starts_and_reaches_the_server(tui: Hop3TUI):
    """The dashboard's health check runs on arrival; `Connecting...` must not stick.

    This is the end-to-end shape of the arrival-fetch bug: every screen used to
    register `ui.every` alone, which sleeps before its first call, so the indicator
    sat on "Connecting..." for thirty seconds against a server that was right there.
    """
    text = draw(app(tui))

    assert "Connected" in text, text[:400]
    assert "Connecting" not in text
