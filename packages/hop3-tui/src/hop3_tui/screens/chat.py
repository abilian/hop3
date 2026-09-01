# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""A command console.

The original had a `CommandSuggester` feeding Textual's `Input`. turbodesk's `textbox`
has no suggester hook, so the completion is shown as a hint under the prompt instead —
the same information, one fewer moving part. See the plan's findings for the gap.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from turbodesk import UI, Size, Style, View, hcat, markup, vcat
from turbodesk.widgets import scroller, textbox

from hop3_tui.api.client import Hop3ClientError
from hop3_tui.screens import Screen
from hop3_tui.screens._common import bind, fill

COMMANDS = [
    "apps",
    "app",
    "start",
    "stop",
    "restart",
    "logs",
    "env",
    "status",
    "clear",
    "help",
    "deploy",
    "backup",
    "restore",
]

BANNER = "[green]Hop3 console.[/] Type [bold]help[/] for commands."


class Line(NamedTuple):
    """One line of transcript. A tuple so the log can live in `ui.state`."""

    text: str
    kind: str = "out"  # out | in | err


# Declared, so the slot holds "any number of lines" rather than "exactly one".
OPENING: tuple[Line, ...] = (Line(BANNER),)


def suggest(prefix: str) -> str | None:
    """The first command `prefix` could grow into. What `CommandSuggester` did."""
    if not prefix:
        return None
    return next((c for c in COMMANDS if c.startswith(prefix) and c != prefix), None)


async def run_command(hop3, command: str) -> list[Line]:
    """Execute one console command and return what to print."""
    verb, _, rest = command.strip().partition(" ")
    match verb:
        case "":
            return []
        case "help":
            return [Line("Commands: " + ", ".join(COMMANDS))]
        case "apps":
            try:
                apps = await hop3.api_client.list_apps()
            except Hop3ClientError as error:
                return [Line(f"error: {error}", "err")]
            return [Line(f"{app.name:<20} {app.state.value}") for app in apps] or [
                Line("(no apps)")
            ]
        case "status":
            return [Line(f"connection: {hop3.connection_state.value}")]
        case "start" | "stop" | "restart" if rest:
            call = getattr(hop3.api_client, f"{verb}_app")
            try:
                await call(rest)
            except Hop3ClientError as error:
                return [Line(f"error: {error}", "err")]
            return [Line(f"{verb}ed {rest}")]
        case "start" | "stop" | "restart":
            return [Line(f"usage: {verb} <app>", "err")]
        case _:
            return [Line(f"unknown command: {verb}", "err")]


def render(
    ui: UI,
    hop3,
    size: Size,
    *,
    argument: str = "",
    push: Callable[..., None] | None = None,
    switch: Callable[[Screen], None] | None = None,
) -> View:
    transcript, set_transcript = ui.state(OPENING)

    prompt = textbox(ui, focus="chat", width=max(10, size.width - 4))
    completion = suggest(prompt.value)

    def submit() -> None:
        entered = prompt.value
        if not entered.strip():
            return
        prompt.set("")
        if entered.strip() == "clear":
            set_transcript(())
            return

        async def run() -> None:
            printed = await run_command(hop3, entered)
            set_transcript((*transcript, Line(f"> {entered}", "in"), *printed))

        ui.spawn(run())

    def complete() -> None:
        if completion:
            prompt.set(completion)

    bind(ui, {"\r": submit, "\t": complete})

    t = ui.theme
    colours = {"in": t.mauve, "err": t.red, "out": t.subtext1}
    body = vcat([
        markup.render(ui.theme, line.text, Style(fg=colours[line.kind]))
        for line in transcript
    ]) or View.text("")
    pane = scroller(
        ui, body, Size(size.width, max(1, size.height - 2)), stick_to_bottom=True
    )
    hint = (
        markup.render(ui.theme, f"[dim]tab → {completion}[/]")
        if completion
        else View.text("")
    )
    return fill(
        ui,
        vcat([
            pane.view,
            hcat([View.text(" > ", Style(fg=t.green, bold=True)), prompt.view]),
            hint,
        ]),
        size,
    )
