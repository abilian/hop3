# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Header, footer and panel frames — what Textual gave us for free.

`Header` and `Footer` were widgets you yielded and a stylesheet positioned. Here they
are functions returning a full-width row, and the screen stacks them itself. That is
the whole of it: about forty lines standing in for two imports and a `.tcss` file.
"""

from __future__ import annotations

from turbodesk import UI, Size, Style, View, hcat, vcat, zcat
from turbodesk.widgets import border

CLOCK_WIDTH = 8


def header(ui: UI, title: str, subtitle: str = "") -> View:
    """The title bar: app name left, status middle, clock right."""
    t = ui.theme
    style = Style(fg=t.crust, bg=t.mauve, bold=True)
    clock = ui.now(tick=1.0).strftime("%H:%M:%S")

    left = View.text(f" {title} ", style)
    right = View.text(f" {clock} ", style)
    room = max(0, ui.size.width - left.width - right.width)
    middle = View.text(subtitle.center(room)[:room], Style(fg=t.crust, bg=t.mauve))
    return hcat([left, middle, right])


def footer(ui: UI, bindings: list[tuple[str, str]]) -> View:
    """The key hints along the bottom, in the order given.

    A hint that will not fit is dropped whole rather than cut in half — `q  Q` reads
    like a different binding, which is worse than not offering the hint at all.
    """
    t = ui.theme
    key = Style(fg=t.crust, bg=t.overlay1, bold=True)
    label = Style(fg=t.subtext0, bg=t.surface0)

    parts: list[View] = []
    used = 0
    for binding, description in bindings:
        chip, caption = f" {binding} ", f" {description} "
        if used + len(chip) + len(caption) > ui.size.width:
            break
        parts += [View.text(chip, key), View.text(caption, label)]
        used += len(chip) + len(caption)
    row = hcat(parts) if parts else View.text("", label)
    return hcat([row, View.text(" " * (ui.size.width - used), label)])


def panel_title(ui: UI, text: str) -> View:
    """The bold caption every panel in the original carried as `.panel-title`."""
    return View.text(text.upper(), Style(fg=ui.theme.subtext0, bold=True))


def panel(ui: UI, title: str, body: View, size: Size, *, accent: bool = False) -> View:
    """A bordered box of a fixed size, so a row of them lines up.

    The original said `border: solid $primary; padding: 1; height: 100%` in CSS and let
    the grid size it. Here the caller works out the size and passes it in.
    """
    t = ui.theme
    inner_width = max(1, size.width - 4)
    inner_height = max(1, size.height - 4)
    content = vcat([
        panel_title(ui, title),
        View.text(""),
        body,
    ])
    overflowing = content.height > inner_height
    content = content.crop(
        right=max(0, content.width - inner_width),
        bottom=max(0, content.height - inner_height),
    )
    if overflowing:
        # Mark the corner rather than truncating in silence: without a layout engine
        # nothing else reports that a panel did not get the room it asked for, and a
        # row that simply vanishes reads as a bug in the data. A corner glyph costs no
        # line, which matters when the panel only has four.
        content = zcat([
            View.text("…", Style(fg=t.peach, bold=True)).pad(
                left=max(0, inner_width - 1), top=max(0, inner_height - 1)
            ),
            content,
        ])
    padded = zcat([
        content,
        View.rect(inner_width, inner_height, Style(bg=t.base)),
    ])
    return border(
        padded,
        line="round",
        padding=1,
        style=Style(fg=t.mauve if accent else t.overlay0, bg=t.base),
    )
