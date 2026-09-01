# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Driving a screen the way a user does: render it, press keys, let the work finish.

Rendering alone proves the drawing. Every mutating operation in this app — start,
stop, delete, detach, restore, deploy — lives in a closure behind a key binding, and
half of them behind a `dialog.confirm`. None of that is reachable without dispatching
real key events and letting the spawned coroutines run, which is what `drive` is for.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from typing import Any

import pytest
from hop3_tui.api.client import Hop3ClientError
from hop3_tui.app import Hop3TUI
from hop3_tui.config import TUIConfig
from hop3_tui.screens import SCREENS, Screen
from turbodesk import Size, View
from turbodesk.events import Event, Key, KeyPress
from turbodesk.runtime import UI, drain
from turbodesk.testing import to_text
from turbodesk.theme import MOCHA

SIZE = Size(90, 24)

#: A dialog's buttons start on the first choice, and `confirm` puts "yes" there.
YES = [KeyPress(Key.ENTER)]
NO = [KeyPress(Key.RIGHT), KeyPress(Key.ENTER)]
CANCEL = [KeyPress(Key.ESCAPE)]


class StubClient:
    """Records every call, and hands back whatever the test set up.

    A recorder rather than a mock: the assertions are about which call the screen
    made with which arguments, not about how it was invoked.
    """

    def __init__(self, **returns: Any) -> None:
        self.returns = returns
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        #: Method names that should raise, for testing the error paths.
        self.fails: set[str] = set()

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name.startswith("_"):
            raise AttributeError(name)

        async def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args))
            if name in self.fails:
                refused = f"{name} refused"
                raise Hop3ClientError(refused)
            # Most read methods return a list; a write method's return is ignored.
            return self.returns.get(name, [])

        return call

    def called(self, name: str) -> bool:
        return any(call == name for call, _ in self.calls)

    def args_for(self, name: str) -> tuple[Any, ...]:
        """The arguments of the first call to `name`. Fails loudly if never called."""
        for call, args in self.calls:
            if call == name:
                return args
        msg = f"{name} was never called; got {[c for c, _ in self.calls]}"
        raise AssertionError(msg)


@pytest.fixture
def client() -> StubClient:
    return StubClient()


@pytest.fixture
def hop3(client: StubClient) -> Hop3TUI:
    """A real `Hop3TUI` with the network swapped out. Nothing else is stubbed."""
    app = Hop3TUI(TUIConfig(server_url="http://localhost:1"))
    app.api_client = client  # type: ignore[assignment]  # ken: a recorder, by design
    return app


@pytest.fixture
def drive(hop3: Hop3TUI) -> Callable[..., str]:
    """Render a screen, press keys one at a time, and return what is on screen.

    Keys go in one at a time with the spawned work settled between them, because
    that is the only order in which a dialog can be answered: pressing `D` spawns a
    coroutine that has not yet opened its modal, so the answering Enter must arrive
    in a later dispatch.
    """

    def run(
        screen: Screen,
        keys: Iterable[Event] = (),
        *,
        argument: str = "",
        size: Size = SIZE,
        pushed: list[tuple[Screen, str]] | None = None,
        switched: list[Screen] | None = None,
    ) -> str:
        def wrapper(ui: UI) -> View:
            with ui.scope(screen):
                return SCREENS[screen](
                    ui,
                    hop3,
                    size,
                    argument=argument,
                    push=lambda s, a="": (pushed if pushed is not None else []).append((
                        s,
                        a,
                    )),
                    switch=(switched if switched is not None else []).append,
                )

        async def scenario() -> str:
            ui = UI(size, MOCHA)
            view = ui.render(wrapper)
            for event in [None, *keys]:
                if event is not None:
                    view = drain(ui, wrapper, view, [event])
                view = await _settle(ui, wrapper, view)
            if ui._failure is not None:
                # What `run` does. Without this a coroutine that raised leaves the
                # screen rendering happily and the test reads it as a pass.
                raise ui._failure
            return to_text(view)

        return asyncio.run(scenario())

    return run


async def _settle(
    ui: UI, app: Callable[[UI], View], view: View, rounds: int = 8
) -> View:
    """Let spawned coroutines run, re-rendering whenever they dirty the frame."""
    for _ in range(rounds):
        await asyncio.sleep(0.01)
        if ui._dirty:
            view = ui.render(app)
    return view
