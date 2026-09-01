# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Scaffolding every screen wants.

`bind` is what Textual's `BINDINGS` list plus its `action_*` naming convention did:
map a key to a callable. Written out, it is a dict and four lines of dispatch.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from turbodesk import UI, Size, Style, View, zcat
from turbodesk.events import Event, KeyPress

Action = Callable[[], None]


def bind(ui: UI, actions: dict[str, Action]) -> None:
    """Run `actions[key]` when that key arrives, and consume it."""

    def keys(event: Event) -> bool:
        if not isinstance(event, KeyPress) or not isinstance(event.key, str):
            return False
        action = actions.get(event.key)
        if action is None:
            return False
        action()
        return True

    ui.on_event(keys)


def poll(ui: UI, interval: float, refresh: Callable[[], Any]) -> None:
    """Fetch on arrival, then every `interval` seconds.

    `ui.every` sleeps before its first call, so a screen registering only that shows
    an empty pane for a whole interval when you arrive on it — thirty seconds, on the
    environment-variable screen. `ui.task` runs once when the hook is first reached,
    which is what covers the arrival.
    """
    ui.task(refresh)
    ui.every(interval, refresh)


def rows(size: Size, *fractions: float) -> list[int]:
    """Split `size.height` into rows by fraction, giving the remainder to the last."""
    heights = [max(1, int(size.height * fraction)) for fraction in fractions[:-1]]
    return [*heights, max(1, size.height - sum(heights))]


def halves(width: int) -> tuple[int, int]:
    """Two columns, the left taking the odd cell. What `grid-size: 2` worked out."""
    left = width // 2 + width % 2
    return left, width - left


def fill(ui: UI, view: View, size: Size) -> View:
    """Crop and pad `view` to exactly `size`, over the theme background."""
    view = view.crop(
        right=max(0, view.width - size.width),
        bottom=max(0, view.height - size.height),
    )
    return zcat([
        view,
        View.rect(size.width, size.height, Style(bg=ui.theme.base)),
    ])


def title_bar(ui: UI, text: str) -> View:
    """A screen's own heading, under the app header."""
    t = ui.theme
    label = f"  {text}  ".ljust(ui.size.width)
    return View.text(label, Style(fg=t.text, bg=t.surface0, bold=True))
